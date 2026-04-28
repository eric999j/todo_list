from viewmodel import ViewModel
from commands.task_commands import AddTaskCommand, DeleteSelectedTasksCommand, UpdateTaskCommand, ToggleDoneStatusCommand, MoveTaskCommand, RemoveLinkCommand
from task import Task


def test_add_undo_redo():
    vm = ViewModel()
    initial_count = len(vm.tasks)

    cmd = AddTaskCommand(vm, task_text="New Task A")
    vm.execute_command(cmd)
    assert len(vm.tasks) == initial_count + 1
    created_id = vm.tasks[-1].id

    vm.undo()
    assert all(t.id != created_id for t in vm.tasks)

    vm.redo()
    # redo should recreate task (may append new id)
    assert len(vm.tasks) == initial_count + 1


def test_update_undo_redo():
    vm = ViewModel()
    a = vm.add_task("Task B")
    tid = a.id
    cmd = UpdateTaskCommand(vm, task_id=tid, new_text="Task B Updated")
    vm.execute_command(cmd)
    assert vm.get_task_by_id(tid).text == "Task B Updated"

    vm.undo()
    assert vm.get_task_by_id(tid).text == "Task B"

    vm.redo()
    assert vm.get_task_by_id(tid).text == "Task B Updated"


def test_toggle_undo_redo():
    vm = ViewModel()
    a = vm.add_task("Task C")
    tid = a.id
    cmd = ToggleDoneStatusCommand(vm, task_ids=[tid])
    vm.execute_command(cmd)
    assert vm.get_task_by_id(tid).is_done is True

    vm.undo()
    assert vm.get_task_by_id(tid).is_done is False

    vm.redo()
    assert vm.get_task_by_id(tid).is_done is True


def test_remove_link_undo_redo():
    vm = ViewModel()
    a = vm.add_task("Task D")
    tid = a.id
    # manually set link
    t = vm.get_task_by_id(tid)
    t.link = "http://example"

    cmd = RemoveLinkCommand(vm, task_id=tid)
    vm.execute_command(cmd)
    assert vm.get_task_by_id(tid).link is None

    vm.undo()
    assert vm.get_task_by_id(tid).link == "http://example"

    vm.redo()
    assert vm.get_task_by_id(tid).link is None


def test_delete_undo_redo():
    vm = ViewModel()
    a = vm.add_task("Task E")
    b = vm.add_task("Task F")
    # add child to a
    a_task = vm.get_task_by_id(a.id)
    child = Task("Child of E")
    a_task.children.append(child)

    # delete a and b
    ids = [a.id, b.id]
    cmd = DeleteSelectedTasksCommand(vm, task_ids=ids, confirmed=True)
    vm.execute_command(cmd)
    assert vm.get_task_by_id(a.id) is None
    assert vm.get_task_by_id(b.id) is None

    vm.undo()
    # after undo both should exist
    assert vm.get_task_by_id(a.id) is not None
    assert vm.get_task_by_id(b.id) is not None

    vm.redo()
    assert vm.get_task_by_id(a.id) is None
    assert vm.get_task_by_id(b.id) is None


def test_delete_undo_rebuilds_index_once():
    vm = ViewModel()
    a = vm.add_task("Task G")
    b = vm.add_task("Task H")
    cmd = DeleteSelectedTasksCommand(vm, task_ids=[a.id, b.id], confirmed=True)
    vm.execute_command(cmd)

    original_rebuild = vm.rebuild_task_index
    call_count = {"value": 0}

    def tracked_rebuild():
        call_count["value"] += 1
        return original_rebuild()

    vm.rebuild_task_index = tracked_rebuild
    vm.undo()

    assert call_count["value"] == 1
    assert vm.get_task_by_id(a.id) is not None
    assert vm.get_task_by_id(b.id) is not None


def test_delete_parent_child_undo():
    vm = ViewModel()
    parent = vm.add_task("Parent")
    child = Task("Child")
    parent_task = vm.get_task_by_id(parent.id)
    parent_task.children.append(child)

    # delete both parent and child (delete by parent id is sufficient)
    cmd = DeleteSelectedTasksCommand(vm, task_ids=[parent.id], confirmed=True)
    vm.execute_command(cmd)
    assert vm.get_task_by_id(parent.id) is None
    assert vm.get_task_by_id(child.id) is None

    vm.undo()
    # parent should be restored and child should be under parent
    p = vm.get_task_by_id(parent.id)
    assert p is not None
    # child restored and found as child of parent
    found_child, _ = vm.find_task_by_id(child.id)
    assert found_child is not None
    parent_after, _ = vm.find_parent_list(child.id)
    assert parent_after is not None and parent_after.id == parent.id


def test_move_undo_redo():
    vm = ViewModel()
    a = vm.add_task("Top 1")
    b = vm.add_task("Top 2")
    c = vm.add_task("Top 3")
    # move c to be child of a (choose bbox and y that fall into middle 25%-75%)
    cmd = MoveTaskCommand(vm, task_id=c.id, target_id=a.id, y=20, bbox=(0,0,100,40), delta_x=0)
    vm.execute_command(cmd)
    # ensure c is now child of a
    found, _ = vm.find_task_by_id(c.id)
    assert found is not None
    parent, _ = vm.find_parent_list(c.id)
    assert parent is not None and parent.id == a.id

    vm.undo()
    # after undo, c should be back at top-level
    parent, _ = vm.find_parent_list(c.id)
    assert parent is None

    vm.redo()
    parent, _ = vm.find_parent_list(c.id)
    assert parent is not None and parent.id == a.id
