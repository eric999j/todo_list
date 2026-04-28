from .base_command import Command
from task import Task
import copy
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import date

class AddTaskCommand(Command):
    """新增任務命令 - Undo 時刪除新增的任務"""
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._added_task_id: Optional[str] = None  # 記錄新增任務的 ID
        self._parent_id: Optional[str] = None       # 記錄父任務 ID
    
    def execute(self) -> bool:
        task_text: Optional[str] = self.params.get("task_text")
        parent_id: Optional[str] = self.params.get("parent_id")
        
        # Collect other potential task attributes
        kwargs = {k: v for k, v in self.params.items() if k not in ["task_text", "parent_id"]}

        if not task_text:
            return False
        
        self._parent_id = parent_id
        new_task = self.app.add_task(task_text, parent_id=parent_id, **kwargs)
        if new_task:
            self._added_task_id = new_task.id
            return True
        return False
    
    def undo(self) -> None:
        """逆向操作：刪除剛剛新增的任務"""
        if self._added_task_id:
            self.app.delete_tasks([self._added_task_id], notify_ui=False)
            self._notify_ui("已復原：移除新增的任務")

class DeleteSelectedTasksCommand(Command):
    """刪除任務命令 - Undo 時還原被刪除的任務
    
    注意：UI 層應在建立此命令前先進行確認對話框，
    此命令不應直接處理 UI 互動。
    """
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        # 儲存被刪除任務的完整資訊 (task_copy, parent_id, index_in_parent)
        self._deleted_tasks: List[Tuple[Task, Optional[str], int]] = []
    
    @staticmethod
    def _is_ancestor_in_set(app: Any, task_id: str, id_set: Set[str]) -> bool:
        """檢查 task_id 的任一祖先是否已在 id_set 中"""
        parent_id = app._parent_index.get(task_id)
        while parent_id:
            if parent_id in id_set:
                return True
            parent_id = app._parent_index.get(parent_id)
        return False

    def execute(self) -> bool:
        task_ids: Optional[List[str]] = self.params.get("task_ids")
        if not task_ids:
            return False

        self._deleted_tasks.clear()
        
        id_set: Set[str] = set(task_ids)
        
        # 先備份要刪除的任務及其位置資訊
        # 過濾掉已被祖先涵蓋的 ID，避免 undo 時重複還原
        for task_id in task_ids:
            if self._is_ancestor_in_set(self.app, task_id, id_set):
                continue
            task, parent_list = self.app.find_task_by_id(task_id)
            if task and parent_list is not None:
                # 找出父任務 ID
                parent_task, _ = self.app.find_parent_list(task_id)
                parent_id = parent_task.id if parent_task else None
                index = parent_list.index(task)
                # 深拷貝以保存完整狀態
                self._deleted_tasks.append((copy.deepcopy(task), parent_id, index))
        
        self.app.delete_tasks(task_ids)
        return True
    
    def undo(self) -> None:
        """逆向操作：還原被刪除的任務到原位置"""
        # 反向插入以維持正確順序
        for task_copy, parent_id, index in reversed(self._deleted_tasks):
            if parent_id:
                parent, _ = self.app.find_task_by_id(parent_id)
                if parent:
                    parent.children.insert(index, task_copy)
                else:
                    # 父任務也被刪除了，插入到頂層
                    self.app.tasks.insert(min(index, len(self.app.tasks)), task_copy)
            else:
                # 原本就在頂層
                self.app.tasks.insert(min(index, len(self.app.tasks)), task_copy)

        # 批次還原後再重建一次索引，避免每筆都重建
        self.app.rebuild_task_index()
        
        self._notify_ui(f"已復原：還原 {len(self._deleted_tasks)} 個任務")

class UpdateTaskCommand(Command):
    """更新任務命令 - Undo 時還原舊值"""
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._old_values: dict = {}  # 儲存舊值以便 undo
        self._task_id: Optional[str] = None
    
    def execute(self) -> bool:
        task_id: Optional[str] = self.params.get("task_id")
        self._task_id = task_id
        
        if not task_id:
            return False
        
        task, _ = self.app.find_task_by_id(task_id)
        if not task:
            return False
        
        # 只備份會被修改的欄位的舊值
        valid_keys = {"new_text", "new_link", "new_priority", "new_due_date", "new_start_date", "new_is_done", "new_project"}
        update_kwargs = {k: v for k, v in self.params.items() if k in valid_keys}
        if not update_kwargs:
            return False
        
        # 記錄舊值
        if "new_text" in update_kwargs:
            self._old_values["new_text"] = task.text
        if "new_link" in update_kwargs:
            self._old_values["new_link"] = task.link
        if "new_priority" in update_kwargs:
            self._old_values["new_priority"] = task.priority
        if "new_due_date" in update_kwargs:
            self._old_values["new_due_date"] = task.due_date
        if "new_start_date" in update_kwargs:
            self._old_values["new_start_date"] = task.start_date
        if "new_is_done" in update_kwargs:
            self._old_values["new_is_done"] = task.is_done
        if "new_project" in update_kwargs:
            self._old_values["new_project"] = task.project
        
        self.app.update_task(task_id, **update_kwargs)
        return True
    
    def undo(self) -> None:
        """逆向操作：還原任務的舊值"""
        if self._task_id and self._old_values:
            self.app.update_task(self._task_id, notify_ui=False, **self._old_values)
            self._notify_ui("已復原：任務更新")

class ToggleDoneStatusCommand(Command):
    """切換完成狀態命令 - Undo 時精確還原所有受影響任務的原始狀態"""
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._task_ids: List[str] = []
        self._original_states: Dict[str, bool] = {}  # 所有受影響任務的原始狀態

    def _collect_subtree_states(self, task: Task) -> None:
        """遞迴收集任務及其子孫的完成狀態"""
        self._original_states[task.id] = task.is_done
        for child in task.children:
            self._collect_subtree_states(child)

    def execute(self) -> bool:
        task_ids: Optional[List[str]] = self.params.get("task_ids")
        if not task_ids:
            return False
        
        self._task_ids = list(task_ids)
        self._original_states.clear()
        
        # 備份所有會被影響的狀態（含子孫與祖先鏈）
        found_any = False
        for tid in task_ids:
            task, _ = self.app.find_task_by_id(tid)
            if task:
                found_any = True
                self._collect_subtree_states(task)
                # 收集祖先鏈的狀態
                parent_id = self.app._parent_index.get(tid)
                while parent_id:
                    parent = self.app._task_index.get(parent_id)
                    if parent:
                        self._original_states[parent.id] = parent.is_done
                    parent_id = self.app._parent_index.get(parent_id)
        
        if not found_any:
            return False

        self.app.toggle_done(task_ids)
        return True
    
    def undo(self) -> None:
        """逆向操作：精確還原每個受影響任務的原始狀態"""
        if self._original_states:
            for tid, was_done in self._original_states.items():
                task, _ = self.app.find_task_by_id(tid)
                if task:
                    task.is_done = was_done
            self._notify_ui("已復原：完成狀態切換")

class MoveTaskCommand(Command):
    """移動任務命令 - Undo 時移回原位置"""
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        # 記錄原始位置資訊
        self._task_id: Optional[str] = None
        self._original_parent_id: Optional[str] = None
        self._original_index: int = 0
    
    def execute(self) -> bool:
        task_id: Optional[str] = self.params.get("task_id")
        target_id: Optional[str] = self.params.get("target_id")
        y: Optional[int] = self.params.get("y")
        bbox: Optional[tuple] = self.params.get("bbox")
        delta_x: Optional[int] = self.params.get("delta_x")
        
        if not task_id:
            return False
        
        self._task_id = task_id
        
        # 先記錄原始位置
        task, source_list = self.app.find_task_by_id(task_id)
        if not task or source_list is None:
            return False

        parent, _ = self.app.find_parent_list(task_id)
        self._original_parent_id = parent.id if parent else None
        self._original_index = source_list.index(task)
        
        self.app.move_task(task_id, target_id=target_id, y=y, bbox=bbox, delta_x=delta_x)
        return True
    
    def undo(self) -> None:
        """逆向操作：將任務移回原位置"""
        if not self._task_id:
            return
        
        task, current_list = self.app.find_task_by_id(self._task_id)
        if not task or current_list is None:
            return
        
        # 從當前位置移除
        try:
            current_list.remove(task)
        except ValueError:
            pass
        
        # 插入回原位置
        if self._original_parent_id:
            parent, _ = self.app.find_task_by_id(self._original_parent_id)
            if parent:
                parent.children.insert(min(self._original_index, len(parent.children)), task)
            else:
                self.app.tasks.insert(min(self._original_index, len(self.app.tasks)), task)
        else:
            self.app.tasks.insert(min(self._original_index, len(self.app.tasks)), task)

        self.app.rebuild_task_index()
        
        self._notify_ui("已復原：任務移動")

class RemoveLinkCommand(Command):
    """移除連結命令 - Undo 時還原連結"""
    
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._task_id: Optional[str] = None
        self._original_link: Optional[str] = None
    
    def execute(self) -> bool:
        task_id: Optional[str] = self.params.get("task_id")
        if not task_id:
            return False
        
        self._task_id = task_id
        
        # 備份原始連結
        task, _ = self.app.find_task_by_id(task_id)
        if task:
            self._original_link = task.link
        
        self.app.remove_link(task_id)
        return bool(self._original_link)
    
    def undo(self) -> None:
        """逆向操作：還原連結"""
        if self._task_id and self._original_link:
            task, _ = self.app.find_task_by_id(self._task_id)
            if task:
                task.link = self._original_link
                self._notify_ui("已復原：還原連結")
