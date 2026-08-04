from typing import Optional, List, Tuple, Any, Set
import copy
from logger import get_logger
from task import Task
from task_manager import TaskManager
from command_history import CommandHistory
from commands.base_command import Command

_logger = get_logger("viewmodel")

class ViewModel:
    """MVVM 的 ViewModel 層：負責協調資料層（TaskManager）、命令歷史與提供給 UI 的介面。"""
    def __init__(self) -> None:
        self.task_manager: TaskManager = TaskManager() # 負責 persist / load
        self.tasks: List[Task] = []
        self.history: CommandHistory = CommandHistory()
        self.ui_manager: Optional[Any] = None
        # 任務 ID 索引：加速 O(1) 查詢
        self._task_index: dict[str, Task] = {}
        # 任務父節點索引：task_id -> parent_id（頂層任務為 None）
        self._parent_index: dict[str, Optional[str]] = {}

    # --- wiring ---
    def set_ui(self, ui_manager: Any) -> None:
        self.ui_manager = ui_manager

    # --- UI notification helpers ---
    def _safe_call(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        """安全呼叫 UI 方法：UI 未注入時直接忽略，例外時記錄但不擴散。"""
        if not self.ui_manager:
            return
        method = getattr(self.ui_manager, method_name, None)
        if method is None:
            return
        try:
            method(*args, **kwargs)
        except Exception:
            _logger.exception("呼叫 UI.%s 失敗", method_name)

    def _notify(self, status: Optional[str] = None, *, redraw: bool = True) -> None:
        """集中化 UI 通知：可選擇是否重繪與更新狀態列。"""
        if redraw:
            self._safe_call("redraw_tree")
        if status is not None:
            self._safe_call("set_status", status)

    def _notify_refresh(self, task_ids: List[str], status: Optional[str] = None) -> None:
        """嘗試做部分更新；UI 回報無法時退回完整重繪。"""
        if not self.ui_manager:
            return
        refresh = getattr(self.ui_manager, "refresh_tasks", None)
        success = False
        if callable(refresh):
            try:
                success = bool(refresh(list(task_ids)))
            except Exception:
                _logger.exception("呼叫 UI.refresh_tasks 失敗")
                success = False
        if not success:
            self._safe_call("redraw_tree")
        if status is not None:
            self._safe_call("set_status", status)

    def _notify_undo_redo(self) -> None:
        self._safe_call("update_undo_redo_buttons")

    # --- command execution ---
    def execute_command(self, command: Command) -> None:
        """統一入口：執行 command，更新 model，儲存與通知 UI"""
        if not command:
            return
        executed = command.execute()
        if executed:
            self.history.record(command)
            self._notify_undo_redo()

    def undo(self) -> None:
        command = self.history.undo()
        if command:
            command.undo()
            self._notify_undo_redo()

    def redo(self) -> None:
        command = self.history.redo()
        if command:
            command.execute()
            self._notify_undo_redo()

    # --- task loading/saving/export ---
    def load_initial_tasks(self) -> None:
        self.tasks, status = self.task_manager.load_tasks()
        self.rebuild_task_index()  # 載入後建立索引
        if self.ui_manager:
            self.ui_manager.redraw_tree()
            self.ui_manager.set_status(status)

    def export_to_markdown(self) -> None:
        status = self.task_manager.export_to_markdown(self.tasks)
        if self.ui_manager:
            self.ui_manager.set_status(status)

    def on_closing(self) -> None:
        status = self.task_manager.save_tasks(self.tasks)
        if self.ui_manager:
            self.ui_manager.set_status(status)
        # UI will handle root.destroy

    # --- helpers for commands / UI ---
    def find_task_by_id(self, task_id: str, task_list: Optional[List[Task]] = None) -> Tuple[Optional[Task], Optional[List[Task]]]:
        """透過 ID 查找任務。若 task_list 為 None，優先使用索引。"""
        if task_list is None:
            task = self._task_index.get(task_id)
            if task:
                parent_list = self._get_parent_list_from_index(task_id)
                if parent_list is not None:
                    return task, parent_list

            # 索引中找不到或結構不同步，回退遞迴搜尋並同步索引
            found, found_list = self._find_task_recursive(task_id, self.tasks)
            if found:
                self.rebuild_task_index()
            return found, found_list

        return self._find_task_recursive(task_id, task_list)

    def _find_task_recursive(self, task_id: str, task_list: List[Task]) -> Tuple[Optional[Task], Optional[List[Task]]]:
        for task in task_list:
            if task.id == task_id:
                return task, task_list
            found, found_list = self._find_task_recursive(task_id, task.children)
            if found:
                return found, found_list
        return None, None

    def _get_parent_list_from_index(self, task_id: str) -> Optional[List[Task]]:
        if task_id not in self._task_index or task_id not in self._parent_index:
            return None

        parent_id = self._parent_index[task_id]
        if parent_id is None:
            return self.tasks

        parent_task = self._task_index.get(parent_id)
        if parent_task is None:
            return None
        return parent_task.children

    def find_parent_list(self, child_id: str) -> Tuple[Optional[Task], Optional[List[Task]]]:
        if child_id in self._task_index and child_id in self._parent_index:
            parent_id = self._parent_index[child_id]
            if parent_id is None:
                return None, None

            parent_task = self._task_index.get(parent_id)
            if parent_task:
                return parent_task, parent_task.children

        parent, parent_list = self._find_parent_recursive(child_id, self.tasks)
        if parent:
            self.rebuild_task_index()
            return parent, parent_list

        # child 可能是頂層任務，補同步索引後維持既有回傳語意 (None, None)
        for task in self.tasks:
            if task.id == child_id:
                self.rebuild_task_index()
                break

        return None, None

    def _find_parent_recursive(self, child_id: str, tasks: List[Task]) -> Tuple[Optional[Task], Optional[List[Task]]]:
        for task in tasks:
            for child in task.children:
                if child.id == child_id:
                    return task, task.children
            found_parent, found_list = self._find_parent_recursive(child_id, task.children)
            if found_parent:
                return found_parent, found_list
        return None, None

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """O(1) 查找任務"""
        return self._task_index.get(task_id)

    # --- 索引管理 ---
    def rebuild_task_index(self) -> None:
        """重建任務 ID 索引"""
        self._task_index.clear()
        self._parent_index.clear()
        self._build_index_recursive(self.tasks, parent_id=None)
    
    def _build_index_recursive(self, tasks: List[Task], parent_id: Optional[str]) -> None:
        for task in tasks:
            self._task_index[task.id] = task
            self._parent_index[task.id] = parent_id
            self._build_index_recursive(task.children, parent_id=task.id)
    
    def _add_to_index(self, task: Task, parent_id: Optional[str]) -> None:
        """將任務及其子任務加入索引"""
        self._task_index[task.id] = task
        self._parent_index[task.id] = parent_id
        for child in task.children:
            self._add_to_index(child, parent_id=task.id)
    
    def _remove_from_index(self, task: Task) -> None:
        """從索引中移除任務及其子任務"""
        self._task_index.pop(task.id, None)
        self._parent_index.pop(task.id, None)
        for child in task.children:
            self._remove_from_index(child)

    def _is_ancestor_selected(self, task_id: str, id_set: Set[str]) -> bool:
        parent_id = self._parent_index.get(task_id)
        while parent_id:
            if parent_id in id_set:
                return True
            parent_id = self._parent_index.get(parent_id)
        return False

    def _filter_descendant_ids(self, task_ids: List[str]) -> List[str]:
        if not task_ids:
            return []

        id_set = set(task_ids)
        for task_id in id_set:
            if task_id not in self._task_index:
                found, _ = self._find_task_recursive(task_id, self.tasks)
                if found:
                    self.rebuild_task_index()
                break

        return [task_id for task_id in task_ids if not self._is_ancestor_selected(task_id, id_set)]

    # --- state helpers ---
    def snapshot_state(self) -> Any:
        """回傳 tasks 的深拷貝，用於命令的 state_backup。"""
        return copy.deepcopy(self.tasks)

    def _set_descendants_done_state(
        self,
        task: Task,
        is_done: bool,
        affected_ids: Optional[Set[str]] = None,
    ) -> int:
        """單次走訪更新所有子孫狀態，並可同步收集受影響 ID。"""
        changed_count = 0
        for child in task.children:
            if affected_ids is not None:
                affected_ids.add(child.id)
            if child.is_done != is_done:
                child.is_done = is_done
                changed_count += 1
            changed_count += self._set_descendants_done_state(child, is_done, affected_ids)
        return changed_count

    def _collect_subtree_ids(self, task: Task, into: Set[str]) -> None:
        into.add(task.id)
        for child in task.children:
            self._collect_subtree_ids(child, into)

    def _set_descendants_project(self, task: Task, project: Optional[str]) -> None:
        """遞迴設定所有子孫的專案名稱。"""
        for child in task.children:
            child.project = project
            self._set_descendants_project(child, project)

    def _mark_parents_undone(self, child_id: str) -> int:
        """當 child 變為未完成，往上將所有祖先標示為未完成。回傳改變的父項數量。"""
        if child_id not in self._task_index or child_id not in self._parent_index:
            found, _ = self._find_task_recursive(child_id, self.tasks)
            if not found:
                return 0
            self.rebuild_task_index()

        count = 0
        parent_id = self._parent_index.get(child_id)
        while parent_id:
            parent = self._task_index.get(parent_id)
            if parent is None:
                self.rebuild_task_index()
                parent = self._task_index.get(parent_id)
                if parent is None:
                    break

            if parent.is_done:
                parent.is_done = False
                count += 1
            
            parent_id = self._parent_index.get(parent.id)
        return count

    def _collect_ancestor_ids(self, task_id: str, into: Set[str]) -> None:
        parent_id = self._parent_index.get(task_id)
        while parent_id:
            into.add(parent_id)
            parent_id = self._parent_index.get(parent_id)

    # --- ViewModel API methods used by Commands ---
    def add_task(self, task_text: str, parent_id: Optional[str] = None, **kwargs) -> Optional[Task]:
        new_task = Task(task_text)
        parent: Optional[Task] = None

        for k, v in kwargs.items():
            if hasattr(new_task, k):
                setattr(new_task, k, v)

        if parent_id:
            parent, _ = self.find_task_by_id(parent_id)
            if parent:
                # 若新任務沒有專案名稱，自動繼承父項專案名稱
                if not new_task.project and parent.project:
                    new_task.project = parent.project
                parent.children.append(new_task)
            else:
                self.tasks.append(new_task)
        else:
            self.tasks.append(new_task)

        self._add_to_index(new_task, parent_id=parent.id if parent else None)

        if self.ui_manager:
            self._safe_call("clear_entry")
            self._notify(f"已新增任務: {task_text}")
            if parent_id:
                tree = getattr(self.ui_manager, "tree", None)
                if tree is not None:
                    try:
                        if tree.exists(parent_id):
                            tree.item(parent_id, open=True)
                    except Exception:
                        _logger.exception("展開父節點失敗：%s", parent_id)
        return new_task

    def delete_tasks(self, task_ids: List[str], notify_ui: bool = True) -> None:
        if not task_ids:
            return

        original_count = len(task_ids)
        filtered_ids = self._filter_descendant_ids(task_ids)
        if not filtered_ids:
            return

        removals: List[Tuple[Task, List[Task]]] = []
        for task_id in filtered_ids:
            task, parent_list = self.find_task_by_id(task_id)
            if task is not None and parent_list is not None:
                removals.append((task, parent_list))

        if not removals:
            return

        for task, _ in removals:
            self._remove_from_index(task)

        for task, parent_list in removals:
            try:
                parent_list.remove(task)
            except ValueError:
                _logger.exception("parent_list 缺少待刪除任務 %s", task.id)

        if notify_ui:
            self._notify(f"已刪除 {original_count} 個任務")

    def update_task(self, task_id: str, notify_ui: bool = True, propagate_project: bool = True, **kwargs) -> None:
        task, _ = self.find_task_by_id(task_id)
        if not task:
            return
        
        if "new_text" in kwargs and kwargs["new_text"] is not None:
            task.text = kwargs["new_text"]
            
        if "new_link" in kwargs:
            val = kwargs["new_link"]
            task.link = val if val else None
            
        if "new_project" in kwargs:
            task.project = kwargs["new_project"]
            if propagate_project:
                self._set_descendants_project(task, kwargs["new_project"])
            
        if "new_priority" in kwargs:
            task.priority = kwargs["new_priority"]
            
        if "new_due_date" in kwargs:
            task.due_date = kwargs["new_due_date"]
            
        if "new_start_date" in kwargs:
            task.start_date = kwargs["new_start_date"]
            
        if "new_is_done" in kwargs and kwargs["new_is_done"] is not None:
            new_is_done = kwargs["new_is_done"]
            prev = bool(task.is_done)
            task.is_done = new_is_done
            # 如果由已完成 -> 未完成，則將父項都設為未完成，且強制把所有子孫標為未完成
            if prev and not task.is_done:
                self._mark_parents_undone(task.id)
                self._set_descendants_done_state(task, False)
            # 如果由未完成 -> 已完成，保留原本邏輯：標示子項為已完成
            if not prev and task.is_done:
                self._set_descendants_done_state(task, True)

        if notify_ui:
            txt = kwargs.get("new_text", task.text)
            self._notify_refresh([task_id], f"任務 '{txt}' 已更新")

    def toggle_done(self, task_ids: List[str]) -> None:
        filtered_ids = self._filter_descendant_ids(task_ids)
        if not filtered_ids:
            return

        last_task_status = False
        affected_count = 0
        affected_ids: Set[str] = set()
        for task_id in filtered_ids:
            task, _ = self.find_task_by_id(task_id)
            if task:
                prev = bool(task.is_done)
                task.is_done = not prev
                last_task_status = task.is_done
                affected_count += 1
                if task.is_done:
                    affected_count += self._set_descendants_done_state(task, True, affected_ids)
                else:
                    affected_count += self._mark_parents_undone(task.id)
                    affected_count += self._set_descendants_done_state(task, False, affected_ids)
                self._collect_subtree_ids(task, affected_ids)
                self._collect_ancestor_ids(task.id, affected_ids)

        status = "標示為已完成" if last_task_status else "標示為未完成"
        self._notify_refresh(list(affected_ids), f"{affected_count} 個任務已{status}")

    def remove_link(self, task_id: str) -> None:
        task, _ = self.find_task_by_id(task_id)
        if task and task.link:
            task.link = None
            self._notify_refresh([task_id], f"已移除任務 '{task.text}' 的連結")
        else:
            self._notify("此任務沒有連結可移除", redraw=False)

    # --- move_task helpers ---
    def _is_valid_move_target(self, task_to_move: Task, target_id: Optional[str]) -> bool:
        """禁止將任務移動到自己子孫之下。"""
        if not target_id:
            return True
        descendant_check, _ = self.find_task_by_id(target_id, task_to_move.children)
        if descendant_check:
            self._notify("無效操作：不能將父項目移動到子項目中", redraw=False)
            return False
        return True

    def _promote_task(self, task_to_move: Task, task_id: str) -> Tuple[str, Optional[str]]:
        """將任務移到目前父項之後（提升一個層級）。回傳狀態訊息與新父 ID。"""
        parent_task, parent_list = self.find_parent_list(task_id)
        if parent_task and parent_list is not None:
            try:
                parent_index = parent_list.index(parent_task)
                parent_list.insert(parent_index + 1, task_to_move)
                grandparent_id = self._parent_index.get(parent_task.id)
                return f"任務 '{task_to_move.text}' 已提升層級", grandparent_id
            except ValueError:
                self.tasks.append(task_to_move)
                return "已移動任務至頂層", None
        self.tasks.append(task_to_move)
        return "已移動任務至頂層", None

    @staticmethod
    def _is_drop_into_target(y: Optional[int], bbox: Optional[tuple]) -> bool:
        """判斷拖放是否落在 target 中段（成為子項）。"""
        if not bbox or not isinstance(y, (int, float)):
            return False
        top = bbox[1]
        height = bbox[3]
        return top + height * 0.25 < y < top + height * 0.75

    def _insert_relative_to_target(
        self,
        task_to_move: Task,
        target_task: Task,
        target_parent_list: List[Task],
        y: Optional[int],
        bbox: Optional[tuple],
    ) -> Tuple[str, Optional[str]]:
        """在 target 同層的前/後插入任務。回傳狀態訊息與新父 ID。"""
        try:
            target_index = target_parent_list.index(target_task)
        except ValueError:
            target_index = None

        if target_index is None:
            self.tasks.append(task_to_move)
            return "已移動任務至頂層", None

        if bbox and isinstance(y, (int, float)):
            midpoint = bbox[1] + bbox[3] / 2
            offset = 0 if y < midpoint else 1
        else:
            offset = 1
        target_parent_list.insert(target_index + offset, task_to_move)
        return "已移動任務", self._parent_index.get(target_task.id)

    def _place_task_at_target(
        self,
        task_to_move: Task,
        target_id: str,
        y: Optional[int],
        bbox: Optional[tuple],
    ) -> Tuple[str, Optional[str]]:
        target_task, target_parent_list = self.find_task_by_id(target_id)
        if target_task is None or target_parent_list is None:
            self.tasks.append(task_to_move)
            return "已移動任務至頂層", None

        if self._is_drop_into_target(y, bbox):
            target_task.children.append(task_to_move)
            return f"任務 '{task_to_move.text}' 已成為 '{target_task.text}' 的子項", target_task.id

        return self._insert_relative_to_target(task_to_move, target_task, target_parent_list, y, bbox)

    def move_task(
        self,
        task_id: str,
        target_id: Optional[str],
        y: Optional[int],
        bbox: Optional[tuple],
        delta_x: Optional[int],
    ) -> None:
        task_to_move, source_list = self.find_task_by_id(task_id)
        if not task_to_move or source_list is None:
            return

        if not self._is_valid_move_target(task_to_move, target_id):
            return

        try:
            source_list.remove(task_to_move)
        except ValueError:
            _logger.exception("source_list 缺少待移動任務 %s", task_id)

        if isinstance(delta_x, (int, float)) and delta_x < -20:
            status, new_parent_id = self._promote_task(task_to_move, task_id)
        elif target_id:
            status, new_parent_id = self._place_task_at_target(task_to_move, target_id, y, bbox)
        else:
            self.tasks.append(task_to_move)
            status = "已移動任務至頂層"
            new_parent_id = None

        self._parent_index[task_to_move.id] = new_parent_id

        # 拖入有專案名稱的父項時，若任務本身無專案則繼承
        if new_parent_id:
            new_parent = self._task_index.get(new_parent_id)
            if new_parent and new_parent.project and not task_to_move.project:
                task_to_move.project = new_parent.project
                self._set_descendants_project(task_to_move, new_parent.project)

        self._notify(status)
