import pytest
from viewmodel import ViewModel


def test_add_task_and_snapshot():
    vm = ViewModel()
    assert vm.tasks == []
    vm.add_task("Task A")
    assert len(vm.tasks) == 1
    snap = vm.snapshot_state()
    assert isinstance(snap, list)
    assert snap[0].text == "Task A"


def test_update_task():
    vm = ViewModel()
    vm.add_task("Old")
    t = vm.tasks[0]
    vm.update_task(t.id, new_text="New")
    assert vm.tasks[0].text == "New"


def test_toggle_done_marks_children():
    vm = ViewModel()
    vm.add_task("Parent")
    parent = vm.tasks[0]
    # create a child task and attach
    from task import Task
    child = Task("Child")
    parent.children.append(child)
    vm.toggle_done([parent.id])
    assert parent.is_done is True
    assert parent.children[0].is_done is True


def test_delete_tasks_removes_nested():
    vm = ViewModel()
    vm.add_task("P1")
    p1 = vm.tasks[0]
    from task import Task
    c1 = Task("C1")
    p1.children.append(c1)
    vm.add_task("P2")
    # delete child by id
    vm.delete_tasks([c1.id])
    assert all(c1.id != ch.id for ch in p1.children)


def test_find_task_by_id_reindexes_after_direct_mutation():
    vm = ViewModel()
    parent = vm.add_task("Parent")
    assert parent is not None

    from task import Task
    child = Task("Child")
    parent.children.append(child)

    # direct mutation bypasses ViewModel index update
    assert vm.get_task_by_id(child.id) is None

    found, containing_list = vm.find_task_by_id(child.id)
    assert found is child
    assert containing_list is parent.children
    # fallback lookup should re-sync indexes
    assert vm.get_task_by_id(child.id) is child

    found_parent, found_parent_list = vm.find_parent_list(child.id)
    assert found_parent is parent
    assert found_parent_list is parent.children
