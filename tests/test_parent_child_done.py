import pytest
from viewmodel import ViewModel
from task import Task


def build_tree(vm: ViewModel):
    vm.add_task("Parent")
    parent = vm.tasks[0]
    # create a subtree
    c1 = Task("Child1")
    c2 = Task("Child2")
    gc = Task("Grandchild")
    c2.children.append(gc)
    parent.children.extend([c1, c2])
    return parent, c1, c2, gc


def test_parent_mark_done_propagates_down():
    vm = ViewModel()
    parent, c1, c2, gc = build_tree(vm)

    # mark parent done -> children and grandchildren become done
    vm.update_task(parent.id, new_is_done=True)
    assert parent.is_done is True
    assert c1.is_done is True
    assert c2.is_done is True
    assert gc.is_done is True


def test_parent_mark_undone_propagates_down():
    vm = ViewModel()
    parent, c1, c2, gc = build_tree(vm)

    # first mark parent done so children become done
    vm.update_task(parent.id, new_is_done=True)
    assert all([parent.is_done, c1.is_done, c2.is_done, gc.is_done])

    # then mark parent undone -> children and grandchildren become undone
    vm.update_task(parent.id, new_is_done=False)
    assert parent.is_done is False
    assert c1.is_done is False
    assert c2.is_done is False
    assert gc.is_done is False


def test_toggle_child_only_does_not_force_others_unrelated():
    vm = ViewModel()
    parent, c1, c2, gc = build_tree(vm)

    # mark only child1 done
    vm.update_task(c1.id, new_is_done=True)
    assert c1.is_done is True
    # parent should become undone (original logic sets parents undone when a child becomes undone; here we set child done so parent remains unchanged)
    # parent should remain False (never set to done automatically when single child set done)
    assert parent.is_done is False
    # other child remains unaffected
    assert c2.is_done is False
