import json
import os
from typing import List, Tuple, Optional, Protocol
from task import Task


class UIFallback(Protocol):
    """ 
    * 定義三個 UI 接口
    * 讓 TaskManager 不直接依賴 tkinter，可以用 mock 或不同 UI 實作注入（便於測試與 headless 執行）。
    * 在 Protocol/介面宣告中保留 ...，可讀性好且符合慣例；若要在執行時明確提示未實作，改用 raise NotImplementedError。
    """

    def show_error(self, title: str, message: str) -> None: ...
    def show_info(self, title: str, message: str) -> None: ...
    def ask_save_path(self, **kwargs) -> Optional[str]: ...


class DefaultUI:
    """ UIFallback具體實作，使用 tkinter 作為預設 UI。"""

    def show_error(self, title: str, message: str) -> None:
        try:
            from tkinter import messagebox
            messagebox.showerror(title, message)
        except Exception:
            # fallback: print to console
            print(f"ERROR: {title} - {message}")

    def show_info(self, title: str, message: str) -> None:
        try:
            from tkinter import messagebox
            messagebox.showinfo(title, message)
        except Exception:
            print(f"INFO: {title} - {message}")

    def ask_save_path(self, **kwargs) -> Optional[str]:
        try:
            from tkinter import filedialog
            return filedialog.asksaveasfilename(**kwargs)
        except Exception:
            return None

class TaskManager:
    """負責處理任務資料的載入、儲存和匯出

    `ui` 可注入以避免在資料層直接呼叫 tkinter，便於測試與 headless 運行。
    """
    def __init__(self, data_file: str = "tasks.json", ui: Optional[UIFallback] = None) -> None:
        # 如果傳入的是相對路徑，將其解析為本模組所在資料夾的絕對路徑，
        # 避免在被系統排程器等以不同工作目錄執行時找不到或無法寫入檔案。
        if not os.path.isabs(data_file):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_file = os.path.join(base_dir, data_file)

        self.data_file: str = data_file
        self.ui: UIFallback = ui if ui is not None else DefaultUI()

    def load_tasks(self) -> Tuple[List[Task], str]:
        """從 JSON 檔案載入任務"""
        if not os.path.exists(self.data_file):
            return [], "找不到任務檔案，已建立新列表。"

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                tasks_data = json.load(f)
            tasks = [Task.from_dict(data) for data in tasks_data]
            return tasks, "任務載入完成"
        except json.JSONDecodeError:
            self.ui.show_error("載入錯誤", f"無法讀取 {self.data_file}，檔案可能已損毀。\n將建立一個新的備份檔案。")
            if os.path.exists(self.data_file):
                os.rename(self.data_file, f"{self.data_file}.bak")
            return [], "錯誤: 任務檔案格式損毀。"
        except (OSError, ValueError, TypeError) as e:
            self.ui.show_error("載入錯誤", f"載入任務時發生錯誤: {e}")
            return [], f"載入時發生未知錯誤: {e}"

    def save_tasks(self, tasks: List[Task]) -> str:
        """將任務儲存到 JSON 檔案"""
        try:
            tasks_data = [task.to_dict() for task in tasks]
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=4)
            return "進度已儲存"
        except PermissionError:
            self.ui.show_error("儲存錯誤", f"無法寫入檔案 {self.data_file}。\n請檢查檔案權限。")
            return "錯誤: 沒有寫入權限。"
        except (OSError, TypeError) as e:
            self.ui.show_error("儲存錯誤", f"儲存任務時發生錯誤: {e}")
            return f"儲存時發生未知錯誤: {e}"

    def export_to_markdown(self, tasks: List[Task]) -> str:
        """將任務結構匯出為 Markdown 檔案"""
        if not tasks:
            self.ui.show_info("匯出", "沒有可匯出的任務。")
            return "沒有可匯出的任務"

        file_path = self.ui.ask_save_path(
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
            title="匯出為 Markdown"
        )

        if not file_path:
            return "已取消匯出"

        try:
            md_content = []
            def build_md(task_list, level, parent_done: bool = False):
                for task in task_list:
                    # effective done: task is done OR inherited from parent
                    effective_done = bool(task.is_done) or bool(parent_done)
                    checkbox = "[x]" if effective_done else "[ ]"

                    # preserve link syntax while embedding checkbox in the bullet
                    if task.link:
                        # produce: - [x] [text](link)
                        md_content.append(f"{'  ' * level}- {checkbox} [{task.text}]({task.link})")
                    else:
                        # produce: - [x] text
                        md_content.append(f"{'  ' * level}- {checkbox} {task.text}")

                    if task.children:
                        # pass down effective_done so children inherit completed state
                        build_md(task.children, level + 1, effective_done)
            
            build_md(tasks, 0)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(md_content))

            self.ui.show_info("匯出成功", "已成功將待辦事項匯出為 Markdown 檔案！")
            return f"成功匯出到 {os.path.basename(file_path)}"

        except Exception as e:
            self.ui.show_error("匯出錯誤", f"匯出時發生錯誤: {e}")
            return f"匯出失敗: {e}"
