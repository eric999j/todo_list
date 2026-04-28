"""效能煙霧測試：1000 節點操作必須在合理時間內完成。"""
import time

from task import Task
from viewmodel import ViewModel


def _build_large_tree(vm: ViewModel, total: int = 1000, branching: int = 10) -> None:
    """建立 total 個任務，每組 branching 個一層父節點，其餘為子節點。"""
    parents = []
    for i in range(total // branching):
        p = vm.add_task(f"P{i}")
        assert p is not None
        parents.append(p)
    for i, parent in enumerate(parents):
        for j in range(branching - 1):
            child = Task(f"C{i}-{j}")
            parent.children.append(child)
    vm.rebuild_task_index()


def test_large_tree_index_lookup_is_fast():
    vm = ViewModel()
    _build_large_tree(vm, total=1000, branching=10)
    start = time.perf_counter()
    # 隨機抽 200 次 O(1) 查找
    sample_ids = list(vm._task_index.keys())[:200]
    for tid in sample_ids:
        assert vm.get_task_by_id(tid) is not None
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05, f"index lookup 過慢: {elapsed:.3f}s"


def test_large_tree_toggle_done_completes_quickly():
    vm = ViewModel()
    _build_large_tree(vm, total=1000, branching=10)
    parent_ids = [t.id for t in vm.tasks]

    start = time.perf_counter()
    vm.toggle_done(parent_ids[:10])
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"toggle_done 過慢: {elapsed:.3f}s"


def test_large_tree_delete_completes_quickly():
    vm = ViewModel()
    _build_large_tree(vm, total=1000, branching=10)
    parent_ids = [t.id for t in vm.tasks]

    start = time.perf_counter()
    vm.delete_tasks(parent_ids[:50])
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"delete_tasks 過慢: {elapsed:.3f}s"
