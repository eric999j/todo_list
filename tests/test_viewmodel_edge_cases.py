"""ViewModel 邊界案例：空輸入、不存在 ID、祖先去重"""
from task import Task
from viewmodel import ViewModel


def test_delete_tasks_with_empty_list_is_noop():
    vm = ViewModel()
    vm.add_task("only")
    vm.delete_tasks([])
    assert len(vm.tasks) == 1


def test_delete_tasks_with_unknown_id_is_noop():
    vm = ViewModel()
    vm.add_task("keep")
    vm.delete_tasks(["does-not-exist"])
    assert len(vm.tasks) == 1


def test_toggle_done_with_empty_list_is_noop():
    vm = ViewModel()
    vm.add_task("a")
    vm.toggle_done([])
    assert vm.tasks[0].is_done is False


def test_toggle_done_filters_descendants_when_ancestor_selected():
    vm = ViewModel()
    parent = vm.add_task("Parent")
    assert parent is not None
    child = Task("Child")
    parent.children.append(child)
    vm.rebuild_task_index()

    # 同時選取 parent 與 child；child 應被當作祖先涵蓋過濾
    vm.toggle_done([parent.id, child.id])
    assert parent.is_done is True
    # child 也已完成（透過 mark_children_done）
    assert child.is_done is True


def test_remove_link_on_task_without_link_does_not_raise():
    vm = ViewModel()
    vm.add_task("no-link")
    # 應安靜處理
    vm.remove_link(vm.tasks[0].id)
    assert vm.tasks[0].link is None


def test_remove_link_with_unknown_id_is_noop():
    vm = ViewModel()
    vm.remove_link("missing")  # 不應拋例外


def test_move_task_into_own_descendant_is_rejected():
    vm = ViewModel()
    parent = vm.add_task("Parent")
    assert parent is not None
    child = Task("Child")
    parent.children.append(child)
    vm.rebuild_task_index()

    # 嘗試把 parent 移入 child（自己的子孫）— 應被拒絕，結構不變
    vm.move_task(parent.id, target_id=child.id, y=None, bbox=None, delta_x=None)
    assert vm.tasks[0] is parent
    assert child in parent.children


def test_update_task_unknown_id_is_noop():
    vm = ViewModel()
    vm.update_task("missing", new_text="x")  # 不應拋例外


def test_filter_descendant_ids_dedupes():
    vm = ViewModel()
    p = vm.add_task("P")
    assert p is not None
    c = Task("C")
    p.children.append(c)
    g = Task("G")
    c.children.append(g)
    vm.rebuild_task_index()

    filtered = vm._filter_descendant_ids([p.id, c.id, g.id])
    assert filtered == [p.id]
