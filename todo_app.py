import tkinter as tk
from typing import Any, List, Optional, Tuple

from logger import get_logger
from task import Task
from ui_manager import UIManager
from viewmodel import ViewModel

_logger = get_logger("app")


class TodoApp:
    """應用程式主控制器（僅負責 UI 與根視窗管理，業務邏輯委由 ViewModel）"""
    def __init__(self, root: tk.Tk) -> None:
        self.root: tk.Tk = root
        self.root.title("待辦事項編排器")
        self.root.geometry("900x750")

        self.viewmodel: ViewModel = ViewModel() # 建立 VM（業務邏輯層）
        self.ui_manager: UIManager = UIManager(root, self.viewmodel) # 把 VM 注入 UI
        self.viewmodel.set_ui(self.ui_manager) # 将 UI 管理器注入 ViewModel（讓 ViewModel 能通知 UI 更新）

        # 將 UIManager 注入 TaskManager，使 TaskManager 使用同一 UI 來顯示訊息
        try:
            if getattr(self.viewmodel, 'task_manager', None):
                self.viewmodel.task_manager.ui = self.ui_manager
        except Exception:
            _logger.exception("注入 UI 至 TaskManager 失敗")

        self.viewmodel.load_initial_tasks()

    def execute_command(self, command: Any) -> None:
        self.viewmodel.execute_command(command)

    def undo(self) -> None:
        self.viewmodel.undo()

    def redo(self) -> None:
        self.viewmodel.redo()

    def load_initial_tasks(self) -> None:
        self.viewmodel.load_initial_tasks()

    def find_task_by_id(self, task_id: str, task_list: Optional[List[Task]] = None) -> Tuple[Optional[Task], Optional[List[Task]]]:
        return self.viewmodel.find_task_by_id(task_id, task_list)
    
    def find_parent_list(self, child_id: str) -> Tuple[Optional[Task], Optional[List[Task]]]:
        return self.viewmodel.find_parent_list(child_id)

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        return self.viewmodel.get_task_by_id(task_id)

    def export_to_markdown(self) -> None:
        self.viewmodel.export_to_markdown()

    def on_closing(self) -> None:
        self.viewmodel.on_closing()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TodoApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)  # 確保關閉時呼叫 on_closing
    root.mainloop()
