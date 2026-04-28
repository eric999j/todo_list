import tkinter as tk
from tkinter import ttk, messagebox, font, filedialog
import webbrowser
import json
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from logger import get_logger
from task import Task
from task_filter import TaskFilter
from commands.task_commands import (
    AddTaskCommand,
    DeleteSelectedTasksCommand,
    UpdateTaskCommand,
    ToggleDoneStatusCommand,
    MoveTaskCommand,
    RemoveLinkCommand,
)

_logger = get_logger("ui")


def _format_short_date(value: Any) -> str:
    """將 date/datetime/str 轉為 'MM/DD' 顯示字串；無法解析時回傳原始字串。"""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d")
        except ValueError:
            return value
    try:
        return value.strftime("%m/%d")
    except Exception:
        return str(value)

class UIManager:
    """負責建立和管理 UI 元件及事件綁定"""
    
    THEMES = {
        "light": {
            "bg": "#ffffff", "fg": "#333333",
            "frame_bg": "#f9f9f9", # Lighter gray for frames
            "entry_bg": "#ffffff", "entry_fg": "#333333",
            "tree_bg": "#ffffff", "tree_fg": "#333333", "tree_field": "#ffffff", "tree_sel": "#e1f0fa",
            "button_bg": "#e1e1e1", "button_fg": "#333333",
            "highlight": "#0078d4",
            "status_bg": "#f0f0f0", "status_fg": "#555555"
        },
        "dark": {
            "bg": "#1e1e1e", "fg": "#e0e0e0",
            "frame_bg": "#252526",
            "entry_bg": "#3c3c3c", "entry_fg": "#ffffff",
            "tree_bg": "#252526", "tree_fg": "#cccccc", "tree_field": "#252526", "tree_sel": "#37373d",
            "button_bg": "#333333", "button_fg": "#cccccc",
            "highlight": "#007acc",
            "status_bg": "#007acc", "status_fg": "#ffffff"
        }
    }

    def __init__(self, root: tk.Tk, viewmodel: Any) -> None:
        self.root: tk.Tk = root
        self.viewmodel: Any = viewmodel # UI 持有 VM，但不直接改資料
        self.tree_item_to_task_id: Dict[str, str] = {}
        self.drag_data: Dict[str, Any] = {}
        self.current_filter: str = "all"
        self.search_query: str = ""
        
        # Theme State
        self.config_file = "config.json"
        self.is_dark_mode = False
        self.load_preferences()
        self.theme = self.THEMES["dark" if self.is_dark_mode else "light"]

        self._setup_ui()
        self._bind_events()
        
        # Apply initial theme
        self.apply_theme()

    def _setup_ui(self) -> None:
        """建立 UI 元件"""
        # Configure Grid Weight for Root
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1) # The treeview row

        # --- Header Frame (Search, Filter, Undo/Redo) ---
        self.header_frame = tk.Frame(self.root)
        self.header_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        
        # Search Frame inside Header
        search_filter_frame = tk.Frame(self.header_frame)
        search_filter_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # 搜尋框
        tk.Label(search_filter_frame, text="🔍", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = tk.Entry(search_filter_frame, width=30, font=("Segoe UI", 10), relief="solid", bd=1)
        self.search_entry.pack(side=tk.LEFT, padx=0)
        self.search_entry.bind("<KeyRelease>", lambda e: self.apply_filter())
        
        # 篩選按鈕
        tk.Label(search_filter_frame, text=" |  篩選:", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(15, 5))
        
        self.filter_var = tk.StringVar(value="all")
        # Radiobutton styling is tricky in tk, we keep it simple or use ttk later
        filters = [
            ("全部", "all"),
            ("未完成", "incomplete"),
            ("高優先", "high_priority"),
            ("已完成", "completed")
        ]
        
        self.filter_radios = []
        for text, value in filters:
            rb = tk.Radiobutton(
                search_filter_frame, 
                text=text, 
                variable=self.filter_var, 
                value=value,
                command=self.apply_filter,
                font=("Segoe UI", 9),
                selectcolor="#dddddd", # Default
                indicatoron=0, # Button-like appearance
                width=8,
                padx=5,
                pady=2,
                relief="flat",
                bd=0
            )
            rb.pack(side=tk.LEFT, padx=2)
            self.filter_radios.append(rb)

        # 復原/重做按鈕 (Move to header right)
        undo_redo_frame = tk.Frame(search_filter_frame)
        undo_redo_frame.pack(side=tk.RIGHT)
        
        self.undo_button = tk.Button(undo_redo_frame, text="↶", command=self.viewmodel.undo, font=("Segoe UI Symbol", 10), state="disabled", width=3, relief="flat")
        self.undo_button.pack(side=tk.LEFT, padx=2)
        
        self.redo_button = tk.Button(undo_redo_frame, text="↷", command=self.viewmodel.redo, font=("Segoe UI Symbol", 10), state="disabled", width=3, relief="flat")
        self.redo_button.pack(side=tk.LEFT, padx=2)

        # --- Input Frame (Add, Export) ---
        self.input_frame = tk.Frame(self.root)
        self.input_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))

        self.entry = tk.Entry(self.input_frame, font=("Segoe UI", 11), relief="solid", bd=1)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=3)
        self.entry.bind("<Return>", lambda e: self.add_task())

        # Clean buttons
        self.add_button = tk.Button(self.input_frame, text="➕ 新增", command=self.add_task, font=("Segoe UI", 9), relief="flat", padx=10, bg="#0078d4", fg="white")
        self.add_button.pack(side=tk.LEFT, padx=2)

        self.export_button = tk.Button(self.input_frame, text="📤 匯出", command=self.export_markdown, font=("Segoe UI", 9), relief="flat", padx=10)
        self.export_button.pack(side=tk.LEFT, padx=2)

        # --- Help/Hint Label ---
        help_text = "💡 提示：輸入任務後按新增添加任務 | 優先級/ 開始/ 截止日上左鍵修改 | 可拖移項目更改階層"
        self.help_label = tk.Label(self.root, text=help_text, font=("Segoe UI", 9), anchor="w")
        self.help_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 0))

        # --- Treeview Frame ---
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=0)
        
        # Treeview Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Treeview 多欄顯示
        columns = ("project", "priority", "start_date", "due_date")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", selectmode="extended", yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)

        # 設定欄位標題
        self.tree.heading("#0", text=" 項目內容")
        self.tree.heading("project", text="專案")
        self.tree.heading("priority", text="優先級")
        self.tree.heading("start_date", text="開始")
        self.tree.heading("due_date", text="截止")
        
        # 設定欄寬
        self.tree.column("#0", width=400, minwidth=200)
        self.tree.column("project", width=100, minwidth=80, anchor="center")
        self.tree.column("priority", width=70, minwidth=50, anchor="center")
        self.tree.column("start_date", width=80, minwidth=70, anchor="center")
        self.tree.column("due_date", width=80, minwidth=70, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Treeview Tags Styling
        self._configure_tree_tags()

        # --- Bottom Bar (Status & Theme Toggle) ---
        self.bottom_bar = tk.Frame(self.root, height=30)
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Status Label
        self.status_label = tk.Label(self.bottom_bar, text="就緒", anchor=tk.W, font=("Segoe UI", 9), padx=10)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Theme Toggle Button (Bottom Right)
        self.theme_toggle_btn = tk.Button(
            self.bottom_bar, 
            text="🌑 / ☀️", 
            command=self.toggle_theme, 
            font=("Segoe UI", 9), 
            relief="flat", 
            bd=0,
            cursor="hand2"
        )
        self.theme_toggle_btn.pack(side=tk.RIGHT, padx=10, pady=2)
        
        # 右鍵選單
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="編輯/加入連結", command=self.edit_task)
        self.context_menu.add_command(label="加入子項", command=self.add_subtask_dialog)
        self.context_menu.add_command(label="標示為已完成", command=self.toggle_done)
        self.context_menu.add_command(label="刪除", command=lambda: self.delete_selected_tasks(confirm=True))
        self.context_menu.add_separator()
        # 開啟連結（僅當項目有 link 時啟用）
        self.context_menu.add_command(label="開啟連結", command=self.open_link)
        self.context_menu.add_command(label="移除連結", command=self.remove_link)

        self.drag_data = {"item": None, "x": 0, "y": 0}
        self.drag_threshold = 8

    def _configure_tree_tags(self):
        default_font_name = "Segoe UI"
        default_size = 10
        
        # Base styles
        self.tree.tag_configure("priority_high", foreground="red")
        self.tree.tag_configure("priority_low", foreground="green")

        # Fonts configuration helper
        def get_font(**kwargs):
            f = font.Font(family=default_font_name, size=default_size)
            for k, v in kwargs.items():
                if hasattr(f, k):
                    f.configure(**{k: v})
                elif k == 'weight' and v == 'bold':
                    f.configure(weight='bold') # Tk font quirk
                else: 
                     # configure directly
                     try: f.config(**{k:v}) 
                     except: pass
            return f

        # Styles
        # 1. Normal Hyperlink
        self.hyperlink_font = get_font(underline=1)
        self.tree.tag_configure("hyperlink", foreground="blue", font=self.hyperlink_font)
        
        # 2. Done
        self.done_font = get_font(overstrike=1)
        self.tree.tag_configure("done", foreground="gray", font=self.done_font)
        
        # 3. Hyperlink + Done
        self.hyperlink_done_font = get_font(underline=1, overstrike=1)
        self.tree.tag_configure("hyperlink_done", foreground="blue", font=self.hyperlink_done_font)

        # 4. Parent (Bold)
        self.parent_font = get_font(weight="bold")
        self.tree.tag_configure("parent", font=self.parent_font)

        # 5. Parent + Done
        self.parent_done_font = get_font(weight="bold", overstrike=1)
        self.tree.tag_configure("parent_done", foreground="gray", font=self.parent_done_font)

        # 6. Parent + Hyperlink
        self.parent_hyperlink_font = get_font(weight="bold", underline=1)
        self.tree.tag_configure("parent_hyperlink", foreground="blue", font=self.parent_hyperlink_font)

        # 7. Parent + Hyperlink + Done
        self.parent_hyperlink_done_font = get_font(weight="bold", underline=1, overstrike=1)
        self.tree.tag_configure("parent_hyperlink_done", foreground="blue", font=self.parent_hyperlink_done_font)

    def load_preferences(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    config = json.load(f)
                    self.is_dark_mode = config.get("dark_mode", False)
            except (OSError, json.JSONDecodeError):
                _logger.exception("讀取偏好設定失敗：%s", self.config_file)

    def save_preferences(self):
        config = {"dark_mode": self.is_dark_mode}
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f)
        except OSError:
            _logger.exception("寫入偏好設定失敗：%s", self.config_file)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.save_preferences()
        self.apply_theme()

    def apply_theme(self):
        mode = "dark" if self.is_dark_mode else "light"
        theme = self.THEMES[mode]
        self.theme = theme

        # 1. Root and standard containers
        self.root.configure(bg=theme["bg"])
        self.header_frame.configure(bg=theme["frame_bg"])
        self.input_frame.configure(bg=theme["bg"])
        
        # 2. Apply to all Frame/Label/Button children recursively or by specific ref
        # Note: Ideally we track them, but for now we have references
        
        # Filter Frame components
        for widget in self.header_frame.winfo_children():
             widget.configure(bg=theme["frame_bg"])
             # Update sub-frames
             for child in widget.winfo_children():
                  if isinstance(child, tk.Label):
                      child.configure(bg=theme["frame_bg"], fg=theme["fg"])
                  elif isinstance(child, tk.Frame):
                      child.configure(bg=theme["frame_bg"])

        # Filter Radios
        for rb in self.filter_radios:
            rb.configure(
                bg=theme["button_bg"], 
                fg=theme["button_fg"], 
                activebackground=theme["highlight"], 
                activeforeground="#ffffff",
                selectcolor=theme["highlight"] if self.is_dark_mode else "#dddddd" 
            )
            # Update select color logic: if selected, it should look distinct.
            # Tk radiobutton indicatoron=0 uses 'selectcolor' for background when selected.
            if mode == "dark":
                rb.configure(selectcolor="#444444")
            else:
                rb.configure(selectcolor="#cccccc")

        # Undo/Redo Buttons
        for btn in [self.undo_button, self.redo_button]:
            btn.configure(bg=theme["button_bg"], fg=theme["button_fg"], activebackground=theme["highlight"], activeforeground="#ffffff")

        # Input Frame components
        self.help_label.configure(bg=theme["bg"], fg="#666666" if not self.is_dark_mode else "#aaaaaa")
        self.entry.configure(bg=theme["entry_bg"], fg=theme["entry_fg"], insertbackground=theme["fg"])
        # Add button has specific color (blue), keep it but maybe adjust shade?
        # Only change text color if needed, keep blue bg for add button
        # Export button
        self.export_button.configure(bg=theme["button_bg"], fg=theme["button_fg"])

        # Bottom Bar
        self.bottom_bar.configure(bg=theme["status_bg"])
        self.status_label.configure(bg=theme["status_bg"], fg=theme["status_fg"])
        self.theme_toggle_btn.configure(bg=theme["status_bg"], fg=theme["status_fg"], activebackground=theme["highlight"])
        self.theme_toggle_btn.config(text="🌙" if not self.is_dark_mode else "☀️")
        
        # Treeview Styles (using ttk.Style)
        style = ttk.Style()
        style.theme_use("clam") # Clam is easier to customize colors than 'vista' or 'xpnative'
        
        style.configure("Treeview", 
            background=theme["tree_bg"],
            foreground=theme["tree_fg"],
            fieldbackground=theme["tree_field"],
            font=("Segoe UI", 10),
            rowheight=25,
            borderwidth=0
        )
        style.map("Treeview", 
            background=[('selected', theme["highlight"])],
            foreground=[('selected', '#ffffff')]
        )
        style.configure("Treeview.Heading",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview.Heading",
             background=[('active', theme["highlight"])],
             foreground=[('active', '#ffffff')]
         )
        
        # Refresh tree tags colors for dark mode readability
        # Hyperlinks need to be lighter in dark mode
        link_color = "#3794ff" if mode == "dark" else "blue"
        self.tree.tag_configure("hyperlink", foreground=link_color)
        self.tree.tag_configure("hyperlink_done", foreground=link_color)
        self.tree.tag_configure("parent_hyperlink", foreground=link_color)
        self.tree.tag_configure("parent_hyperlink_done", foreground=link_color)
        
        priority_high = "#ff5555" if mode == "dark" else "red"
        priority_low = "#55aa55" if mode == "dark" else "green"
        self.tree.tag_configure("priority_high", foreground=priority_high)
        self.tree.tag_configure("priority_low", foreground=priority_low)

        # 搜尋結果標註
        search_match_bg = "#666633" if mode == "dark" else "#fff2cc"
        self.tree.tag_configure("search_match", background=search_match_bg)

        # Force redraw tasks to ensure tags are re-applied if needed (usually direct tag config is enough)


    def on_search_change(self, event: Any) -> None:
        """當搜尋框內容改變時觸發"""
        self.search_query = self.search_entry.get()
        self.redraw_tree()

    def on_filter_change(self) -> None:
        """當篩選選項改變時觸發"""
        self.current_filter = self.filter_var.get()
        self.redraw_tree()

    def on_column_click(self, event: Any) -> None:
        """當點擊 Treeview 的欄位時觸發，用於編輯優先級和截止日期"""
        # 識別點擊的區域
        region = self.tree.identify_region(event.x, event.y)
        
        # 允許 cell (資料欄位), text (主欄位文字), tree (主欄位圖示/縮排)
        # 注意：主欄位 (#0) 通常透過雙擊編輯，單擊主要用於選取
        if region not in ("cell", "text", "tree"):
            return
        
        # 識別點擊的欄位和項目
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        
        if not item or item not in self.tree_item_to_task_id:
            return
        
        task_id = self.tree_item_to_task_id[item]
        task, _ = self.viewmodel.find_task_by_id(task_id)
        
        if not task:
            return

        # 取得欄位位置以對齊選單
        bbox = self.tree.bbox(item, column=column)
        if not bbox:
            return
        
        x, y, w, h = bbox
        menu_x = self.tree.winfo_rootx() + x
        menu_y = self.tree.winfo_rooty() + y + h

        # 根據點擊的欄位顯示相應的編輯界面
        # Treeview columns: #0=Content, #1=Project, #2=Priority, #3=Start Date, #4=Due Date
        if column == "#2":  # Priority 欄位
            self.show_priority_menu(task, menu_x, menu_y)
        elif column == "#3":  # Start Date 欄位
            self.show_date_entry(task, menu_x, menu_y, is_start_date=True)
        elif column == "#4":  # Due Date 欄位
            self.show_date_entry(task, menu_x, menu_y, is_start_date=False)
        # Project (#1) single click -> No reaction

    def show_status_menu(self, event: Any, task: Task) -> None:
        """顯示狀態切換選單"""
        menu = tk.Menu(self.root, tearoff=0)
        
        if task.is_done:
            menu.add_command(
                label="✓ 已完成",
                state=tk.DISABLED
            )
            menu.add_command(
                label="標記為未完成",
                command=lambda t=task: self.toggle_task_status(t)
            )
        else:
            menu.add_command(
                label="標記為已完成",
                command=lambda t=task: self.toggle_task_status(t)
            )
        
        menu.post(event.x_root, event.y_root)

    def show_priority_menu(self, task: Task, x: int, y: int) -> None:
        """顯示優先級選擇選單 (Aligned)"""
        menu = tk.Menu(self.root, tearoff=0)
        
        priorities = [
            ("低優先級", "low"),
            ("一般", "normal"),
            ("高優先級", "high")
        ]
        
        for label, priority_value in priorities:
            # 在當前優先級旁加上勾選標記
            display_label = f"✓ {label}" if task.priority == priority_value else label
            menu.add_command(
                label=display_label,
                command=lambda p=priority_value, t=task: self.update_task_priority(t, p)
            )
        
        menu.post(x, y)

    def show_date_entry(self, task: Task, x: int, y: int, is_start_date: bool = False) -> None:
        """顯示日期輸入選單 (Aligned)"""
        menu = tk.Menu(self.root, tearoff=0)
        
        update_func = self.update_task_start_date if is_start_date else self.update_task_date
        current_date_val = task.start_date if is_start_date else task.due_date

        # 今天
        menu.add_command(
            label="今天",
            command=lambda t=task: update_func(t, datetime.now().date())
        )
        
        # 明天
        from datetime import timedelta
        tomorrow = datetime.now().date() + timedelta(days=1)
        menu.add_command(
            label="明天",
            command=lambda t=task: update_func(t, tomorrow)
        )
        
        # 下週
        next_week = datetime.now().date() + timedelta(days=7)
        menu.add_command(
            label="下週",
            command=lambda t=task: update_func(t, next_week)
        )
        
        menu.add_separator()
        
        # 自訂日期
        menu.add_command(
            label="自訂日期...",
            command=lambda t=task: self.show_date_dialog(t, is_start_date)
        )
        
        # 清除日期
        if current_date_val:
            menu.add_separator()
            menu.add_command(
                label="清除日期",
                command=lambda t=task: update_func(t, None)
            )
        
        menu.post(x, y)

    def toggle_task_status(self, task: Task) -> None:
        """切換任務的完成狀態"""
        cmd = ToggleDoneStatusCommand(
            self.viewmodel,
            task_ids=[task.id]
        )
        self.viewmodel.execute_command(cmd)

    def update_task_priority(self, task: Task, new_priority: str) -> None:
        """更新任務的優先級"""
        if task.priority == new_priority:
            return
        
        cmd = UpdateTaskCommand(
            self.viewmodel,
            task_id=task.id,
            new_text=task.text,
            new_link=task.link,
            new_priority=new_priority,
            new_due_date=task.due_date,
            new_start_date=task.start_date,
            new_project=task.project
        )
        self.viewmodel.execute_command(cmd)

    def update_task_start_date(self, task: Task, new_date: Optional[Any]) -> None:
        """更新任務的開始日期"""
        if task.start_date == new_date:
            return
        
        # 檢查日期邏輯
        if new_date and task.due_date:
            if new_date > task.due_date:
                messagebox.showwarning("日期錯誤", "開始日期不能晚於截止日期")
                return
        
        cmd = UpdateTaskCommand(
            self.viewmodel,
            task_id=task.id,
            new_text=task.text,
            new_link=task.link,
            new_priority=task.priority,
            new_due_date=task.due_date,
            new_start_date=new_date,
            new_project=task.project
        )
        self.viewmodel.execute_command(cmd)

    def update_task_date(self, task: Task, new_date: Optional[Any]) -> None:
        """更新任務的截止日期"""
        if task.due_date == new_date:
            return
        
        # 檢查日期邏輯
        if new_date and task.start_date:
            if new_date < task.start_date:
                messagebox.showwarning("日期錯誤", "截止日期不能早於開始日期")
                return
        
        cmd = UpdateTaskCommand(
            self.viewmodel,
            task_id=task.id,
            new_text=task.text,
            new_link=task.link,
            new_priority=task.priority,
            new_due_date=new_date,
            new_start_date=task.start_date,
            new_project=task.project
        )
        self.viewmodel.execute_command(cmd)

    def show_date_dialog(self, task: Task, is_start_date: bool = False) -> None:
        """顯示自訂日期輸入對話框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("設定開始日期" if is_start_date else "設定截止日期")
        dialog.geometry("280x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 置中顯示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        frame = tk.Frame(dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="日期格式: YYYY-MM-DD", font=("Arial", 9)).pack(anchor=tk.W)
        
        date_entry = tk.Entry(frame, font=("Arial", 11), width=20)
        date_entry.pack(pady=(5, 10), ipady=3)
        
        target_date = task.start_date if is_start_date else task.due_date

        # 預填當前日期或今天
        if target_date:
            date_entry.insert(0, target_date.strftime("%Y-%m-%d"))
        else:
            date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        date_entry.select_range(0, tk.END)
        date_entry.focus()
        
        def save_date() -> None:
            date_str = date_entry.get().strip()
            try:
                from datetime import datetime as dt
                new_date = dt.strptime(date_str, "%Y-%m-%d").date()
                if is_start_date:
                    self.update_task_start_date(task, new_date)
                else:
                    self.update_task_date(task, new_date)
                dialog.destroy()
            except ValueError:
                messagebox.showerror("格式錯誤", "請輸入正確的日期格式: YYYY-MM-DD")
        
        button_frame = tk.Frame(frame)
        button_frame.pack()
        
        tk.Button(button_frame, text="確定", command=save_date, width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="取消", command=dialog.destroy, width=8).pack(side=tk.LEFT)
        
        date_entry.bind("<Return>", lambda e: save_date())
        date_entry.bind("<Escape>", lambda e: dialog.destroy())

    def on_double_click(self, event: Any) -> None:
        """雙擊時編輯任務"""
        self.edit_task()

    def _bind_events(self) -> None:
        """綁定所有事件"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Delete>", self.delete_selected_tasks)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Button-1>", self.on_tree_click)
        # 啟用拖放支援：允許按下、拖曳與放開事件（保留其他 handler，使用 add='+'）
        self.tree.bind("<ButtonPress-1>", self.on_b1_press, add='+')
        self.tree.bind("<B1-Motion>", self.on_b1_motion, add='+')
        self.tree.bind("<ButtonRelease-1>", self.on_b1_release, add='+')
        self.tree.bind("<ButtonRelease-1>", self.on_column_click, add='+')
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        
        # 鍵盤快捷鍵
        self.root.bind("<Control-z>", lambda event: self.viewmodel.undo())
        self.root.bind("<Control-y>", lambda event: self.viewmodel.redo())

    def _on_closing(self) -> None:
        try:
            self.viewmodel.on_closing()
        except Exception:
            _logger.exception("關閉視窗時 ViewModel.on_closing 失敗")
        self.root.destroy()

    # --- Command-issuing methods ---

    def export_markdown(self) -> None:
        """匯出為 Markdown 檔案"""
        self.viewmodel.export_to_markdown()

    def add_task(self) -> None:
        """新增任務"""
        from commands.task_commands import AddTaskCommand
        text = self.entry.get().strip()
        if text:
            command = AddTaskCommand(self.viewmodel, task_text=text)
            self.viewmodel.execute_command(command) # 將變更委派給 ViewModel
            self.entry.delete(0, tk.END)
            self.redraw_tree()
    
    def delete_selected_tasks(self, confirm: bool = True) -> None:
        """刪除選中的任務"""
        from commands.task_commands import DeleteSelectedTasksCommand
        selected_tree_items = list(self.tree.selection())
        # Convert tree item iids to actual task ids (safeguard)
        selected_ids = [self.tree_item_to_task_id.get(i, i) for i in selected_tree_items]
        if not selected_ids:
            return
        
        if confirm:
            count = len(selected_ids)
            result = messagebox.askyesno(
                "確認刪除",
                f"確定要刪除選中的 {count} 個任務嗎？\n(可使用 Ctrl+Z 復原)"
            )
            if not result:
                return

        # tell command that confirmation already done
        command = DeleteSelectedTasksCommand(self.viewmodel, task_ids=selected_ids)
        self.viewmodel.execute_command(command)
        self.redraw_tree()
    
    def edit_task(self) -> None:
        """編輯選中的任務"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        task = self.viewmodel.get_task_by_id(item_id)
        if not task:
            return
        
        # 創建編輯視窗
        edit_window = tk.Toplevel(self.root)
        edit_window.title("編輯任務")
        edit_window.geometry("400x550")
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # 專案名稱
        tk.Label(edit_window, text="專案名稱:", font=("Arial", 10)).pack(pady=(10, 5))
        project_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        project_entry.insert(0, task.project or "")
        project_entry.pack(pady=5)

        # 任務內容
        tk.Label(edit_window, text="任務內容:", font=("Arial", 10)).pack(pady=(10, 5))
        text_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        text_entry.insert(0, task.text)
        text_entry.pack(pady=5)
        
        # 優先級
        tk.Label(edit_window, text="優先級:", font=("Arial", 10)).pack(pady=(10, 5))
        priority_var = tk.StringVar(value=task.priority)
        priority_frame = tk.Frame(edit_window)
        priority_frame.pack(pady=5)
        
        tk.Radiobutton(priority_frame, text="低", variable=priority_var, value="low").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="普通", variable=priority_var, value="normal").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="高", variable=priority_var, value="high").pack(side=tk.LEFT, padx=5)
        
        date_values = ["今天", "明天", "下週"]

        # 開始日期
        tk.Label(edit_window, text="開始日期:", font=("Arial", 10)).pack(pady=(10, 5))
        # 預設為建立日期，但若 task 已經有 start_date 則使用之
        current_start_date = str(task.start_date) if task.start_date else (str(task.creation_time.date()) if task.creation_time else "")
        start_date_values = date_values.copy()
        if current_start_date and current_start_date not in start_date_values:
            start_date_values.append(current_start_date)
        start_date_combo = ttk.Combobox(edit_window, values=start_date_values, width=37, font=("Arial", 11))
        start_date_combo.pack(pady=5)
        if current_start_date:
            start_date_combo.set(current_start_date)

        # 截止日期 (改為 Combobox)
        tk.Label(edit_window, text="截止日期:", font=("Arial", 10)).pack(pady=(10, 5))
        
        current_date_val = str(task.due_date) if task.due_date else ""
        due_date_values = date_values.copy()
        if current_date_val and current_date_val not in due_date_values:
            due_date_values.append(current_date_val)
        
        due_date_combo = ttk.Combobox(edit_window, values=due_date_values, width=37, font=("Arial", 11))
        due_date_combo.pack(pady=5)
        if current_date_val:
            due_date_combo.set(current_date_val)

        # 狀態 (已完成/未完成)
        tk.Label(edit_window, text="狀態:", font=("Arial", 10)).pack(pady=(10, 5))
        status_frame = tk.Frame(edit_window)
        status_frame.pack(pady=5)
        status_var = tk.BooleanVar(value=task.is_done)
        
        tk.Radiobutton(status_frame, text="未完成", variable=status_var, value=False).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(status_frame, text="已完成", variable=status_var, value=True).pack(side=tk.LEFT, padx=5)
        
        # 超連結
        tk.Label(edit_window, text="超連結 (URL):", font=("Arial", 10)).pack(pady=(10, 5))
        link_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        link_entry.insert(0, task.link or "")
        link_entry.pack(pady=5)
        
        # 儲存邏輯
        def save_changes():
            from commands.task_commands import UpdateTaskCommand
            from datetime import datetime, timedelta
            
            new_project = project_entry.get().strip() or None
            new_text = text_entry.get().strip()
            new_priority = priority_var.get()
            new_link = link_entry.get().strip() or None
            new_is_done = status_var.get()
            
            # 開始日期處理
            start_date_val = start_date_combo.get().strip()
            new_start_date = None
            try:
                if start_date_val == "今天":
                    new_start_date = datetime.now().date()
                elif start_date_val == "明天":
                    new_start_date = (datetime.now() + timedelta(days=1)).date()
                elif start_date_val == "下週":
                    new_start_date = (datetime.now() + timedelta(days=7)).date()
                elif not start_date_val:
                    new_start_date = None
                else:
                    new_start_date = datetime.strptime(start_date_val, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("日期錯誤", "開始日期格式不正確，請使用 YYYY-MM-DD 格式")
                return

            # 截止日期處理
            date_val = due_date_combo.get().strip()
            new_due_date = None
            
            try:
                if date_val == "今天":
                    new_due_date = datetime.now().date()
                elif date_val == "明天":
                    new_due_date = (datetime.now() + timedelta(days=1)).date()
                elif date_val == "下週":
                    new_due_date = (datetime.now() + timedelta(days=7)).date()
                elif not date_val:
                    new_due_date = None
                else:
                    new_due_date = datetime.strptime(date_val, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("日期錯誤", "截止日期格式不正確，請使用 YYYY-MM-DD 格式")
                return

            # 日期邏輯檢查
            if new_start_date and new_due_date:
                if new_due_date < new_start_date:
                    messagebox.showerror("日期錯誤", "截止日期不能早於開始日期")
                    return

            if new_text:
                command = UpdateTaskCommand(
                    self.viewmodel,
                    task_id=item_id,
                    new_text=new_text,
                    new_priority=new_priority,
                    new_due_date=new_due_date,
                    new_start_date=new_start_date,
                    new_link=new_link,
                    new_is_done=new_is_done,
                    new_project=new_project
                )
                self.viewmodel.execute_command(command)
                self.redraw_tree()
                
            edit_window.destroy()
        
        # 按鈕區域
        button_frame = tk.Frame(edit_window)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="儲存", command=save_changes, font=("Arial", 10), width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="取消", command=edit_window.destroy, font=("Arial", 10), width=10).pack(side=tk.LEFT, padx=5)
        
        text_entry.focus_set()
        edit_window.bind("<Return>", lambda e: save_changes())
        edit_window.bind("<Escape>", lambda e: edit_window.destroy())

    def add_subtask_dialog(self) -> None:
        """顯示新增子任務視窗"""
        selected = self.tree.selection()
        if not selected:
            return
        
        parent_id = selected[0]
        parent_task = self.viewmodel.get_task_by_id(parent_id)
        if not parent_task:
            return

        # 創建編輯視窗
        edit_window = tk.Toplevel(self.root)
        edit_window.title("新增子任務")
        edit_window.geometry("400x550")
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # 專案名稱
        tk.Label(edit_window, text="專案名稱:", font=("Arial", 10)).pack(pady=(10, 5))
        project_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        if parent_task.project:
            project_entry.insert(0, parent_task.project)
        project_entry.pack(pady=5)

        # 任務內容
        tk.Label(edit_window, text="任務內容:", font=("Arial", 10)).pack(pady=(10, 5))
        text_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        text_entry.pack(pady=5)
        text_entry.focus_set()
        
        # 優先級
        tk.Label(edit_window, text="優先級:", font=("Arial", 10)).pack(pady=(10, 5))
        priority_var = tk.StringVar(value="normal")
        priority_frame = tk.Frame(edit_window)
        priority_frame.pack(pady=5)
        
        tk.Radiobutton(priority_frame, text="低", variable=priority_var, value="low").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="普通", variable=priority_var, value="normal").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="高", variable=priority_var, value="high").pack(side=tk.LEFT, padx=5)
        
        date_values = ["今天", "明天", "下週"]

        # 開始日期 (Default to today)
        tk.Label(edit_window, text="開始日期:", font=("Arial", 10)).pack(pady=(10, 5))
        from datetime import datetime
        current_start_date = str(datetime.now().date())
        start_date_values = date_values.copy()
        if current_start_date not in start_date_values:
            start_date_values.append(current_start_date)
        start_date_combo = ttk.Combobox(edit_window, values=start_date_values, width=37, font=("Arial", 11))
        start_date_combo.pack(pady=5)
        if current_start_date:
            start_date_combo.set(current_start_date)

        # 截止日期
        tk.Label(edit_window, text="截止日期:", font=("Arial", 10)).pack(pady=(10, 5))
        due_date_combo = ttk.Combobox(edit_window, values=date_values, width=37, font=("Arial", 11))
        due_date_combo.pack(pady=5)
        
        # 超連結
        tk.Label(edit_window, text="超連結 (URL):", font=("Arial", 10)).pack(pady=(10, 5))
        link_entry = tk.Entry(edit_window, width=40, font=("Arial", 11))
        link_entry.pack(pady=5)
        
        # 儲存邏輯
        def save_new_subtask():
            from commands.task_commands import AddTaskCommand
            from datetime import datetime, timedelta
            
            new_project = project_entry.get().strip() or None
            new_text = text_entry.get().strip()
            new_priority = priority_var.get()
            new_link = link_entry.get().strip() or None
            
            if not new_text:
                messagebox.showwarning("警告", "任務內容不能為空")
                return

            # 開始日期處理
            start_date_val = start_date_combo.get().strip()
            new_start_date = None
            try:
                if start_date_val == "今天":
                    new_start_date = datetime.now().date()
                elif start_date_val == "明天":
                    new_start_date = (datetime.now() + timedelta(days=1)).date()
                elif start_date_val == "下週":
                    new_start_date = (datetime.now() + timedelta(days=7)).date()
                elif not start_date_val:
                    new_start_date = None
                else:
                    new_start_date = datetime.strptime(start_date_val, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("日期錯誤", "開始日期格式不正確，請使用 YYYY-MM-DD 格式")
                return

            # 截止日期處理
            date_val = due_date_combo.get().strip()
            new_due_date = None
            try:
                if date_val == "今天":
                    new_due_date = datetime.now().date()
                elif date_val == "明天":
                    new_due_date = (datetime.now() + timedelta(days=1)).date()
                elif date_val == "下週":
                    new_due_date = (datetime.now() + timedelta(days=7)).date()
                elif not date_val:
                    new_due_date = None
                else:
                    new_due_date = datetime.strptime(date_val, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("日期錯誤", "截止日期格式不正確，請使用 YYYY-MM-DD 格式")
                return
            
            # 日期邏輯檢查
            if new_start_date and new_due_date:
                if new_due_date < new_start_date:
                    messagebox.showerror("日期錯誤", "截止日期不能早於開始日期")
                    return

            command = AddTaskCommand(
                self.viewmodel,
                task_text=new_text,
                parent_id=parent_id,
                project=new_project,
                priority=new_priority,
                link=new_link,
                start_date=new_start_date,
                due_date=new_due_date
            )
            self.viewmodel.execute_command(command)
            edit_window.destroy()

        # 按鈕區域
        button_frame = tk.Frame(edit_window)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="儲存", command=save_new_subtask, font=("Arial", 10), width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="取消", command=edit_window.destroy, font=("Arial", 10), width=10).pack(side=tk.LEFT, padx=5)
        
        edit_window.bind("<Return>", lambda e: save_new_subtask())
        edit_window.bind("<Escape>", lambda e: edit_window.destroy())
    
    def toggle_done(self) -> None:
        """切換任務完成狀態"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        self._toggle_task_done(item_id)

    def _toggle_task_done(self, item_id: str) -> None:
        """內部用：包裝 ToggleDoneStatusCommand，接受 tree item id 或 task id。"""
        # 支援傳入 tree 的 iid（我們使用 task.id 作為 iid）
        task_id = item_id
        from commands.task_commands import ToggleDoneStatusCommand
        cmd = ToggleDoneStatusCommand(self.viewmodel, task_ids=[task_id])
        self.viewmodel.execute_command(cmd)
        self.redraw_tree()
    
    def remove_link(self) -> None:
        """移除任務的超連結"""
        from commands.task_commands import RemoveLinkCommand
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        command = RemoveLinkCommand(self.viewmodel, task_id=item_id)
        self.viewmodel.execute_command(command)
        self.redraw_tree()

    # --- UI Helper methods ---

    def get_entry_text(self) -> str:
        return self.entry.get().strip()

    def clear_entry(self) -> None:
        self.entry.delete(0, tk.END)

    def set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def show_error(self, title: str, message: str) -> None:
        """供 TaskManager 呼叫的錯誤顯示介面（delegate 到 messagebox）"""
        try:
            messagebox.showerror(title, message)
        except Exception:
            _logger.exception("顯示錯誤對話框失敗：%s", title)
            try:
                self.set_status(f"錯誤: {message}")
            except Exception:
                _logger.exception("更新狀態列失敗")

    def show_info(self, title: str, message: str) -> None:
        """供 TaskManager 呼叫的資訊顯示介面（delegate 到 messagebox）"""
        try:
            messagebox.showinfo(title, message)
        except Exception:
            _logger.exception("顯示資訊對話框失敗：%s", title)
            try:
                self.set_status(message)
            except Exception:
                _logger.exception("更新狀態列失敗")

    def ask_save_path(self, **kwargs) -> Optional[str]:
        """供 TaskManager 呼叫以取得儲存檔案路徑（delegate 到 filedialog）"""
        try:
            return filedialog.asksaveasfilename(parent=self.root, **kwargs)
        except Exception:
            _logger.exception("開啟儲存對話框失敗")
            return None

    def redraw_tree(self) -> None:
        """根據篩選條件重繪整個任務樹"""
        def _gather_opened(parent: str) -> set:
            opened = set()
            for cid in self.tree.get_children(parent):
                try:
                    if self.tree.item(cid, 'open'):
                        opened.add(cid)
                        opened |= _gather_opened(cid)
                except Exception:
                    _logger.debug("讀取展開狀態失敗：%s", cid, exc_info=True)
            return opened

        opened_items = _gather_opened("")

        self.tree.delete(*self.tree.get_children())
        
        # 應用篩選
        search_text = self.search_entry.get().lower()
        filter_mode = self.filter_var.get()
        
        # 首先根據篩選模式篩選
        if filter_mode == "incomplete":
            filtered_tasks = TaskFilter.filter_incomplete(self.viewmodel.tasks)
            use_wrapped = True
        elif filter_mode == "high_priority":
            filtered_tasks = TaskFilter.filter_high_priority(self.viewmodel.tasks)
            use_wrapped = True
        elif filter_mode == "completed":
            filtered_tasks = TaskFilter.filter_completed(self.viewmodel.tasks)
            use_wrapped = True
        else:
            filtered_tasks = self.viewmodel.tasks
            use_wrapped = False
        
        # 再應用搜尋
        if search_text:
            filtered_tasks = TaskFilter.search_tasks(filtered_tasks, search_text)
            use_wrapped = True
        
        self.tree_item_to_task_id.clear()
        self._insert_tasks_recursive(filtered_tasks, "", query=search_text, use_wrapped=use_wrapped)

        # 還原展開狀態（只有在該 iid 現存在時才還原）
        for oid in opened_items:
            if self.tree.exists(oid):
                try:
                    self.tree.item(oid, open=True)
                except Exception:
                    _logger.debug("還原展開狀態失敗：%s", oid, exc_info=True)

    def _insert_tasks_recursive(self, tasks: List[Any], parent: str, parent_is_done: bool = False, query: str = "", use_wrapped: bool = False) -> None:
        """遞迴插入任務到 Treeview，並根據父項狀態決定樣式"""
        for i, node in enumerate(tasks, 1):
            task = node.task if use_wrapped else node
            children = node.children if use_wrapped else task.children
            priority_text = {"low": "低", "normal": "普通", "high": "高"}.get(task.priority, "普通")
            start_date_text = _format_short_date(task.start_date)
            due_date_text = _format_short_date(task.due_date)

            item_id = self.tree.insert(
                parent,
                "end",
                iid=task.id,
                text=f"{i}. {task.text}",
                values=(task.project or "", priority_text, start_date_text, due_date_text)
            )
            self.tree_item_to_task_id[item_id] = task.id
            
            # 設定標籤（樣式）：只有「非子項」（即 parent == ""）顯示為粗體
            tags = []
            is_effectively_done = task.is_done or parent_is_done
            is_child = bool(parent)  # parent 為空字串表示為頂層（非子項）

            if not is_child:
                # 非子項（頂層/非被包含的項目）使用父項（粗體）樣式
                if is_effectively_done and task.link:
                    tags.append("parent_hyperlink_done")
                elif is_effectively_done:
                    tags.append("parent_done")
                elif task.link:
                    tags.append("parent_hyperlink")
                else:
                    tags.append("parent")
            else:
                # 子項則使用非粗體的完成/連結樣式
                if is_effectively_done and task.link:
                    tags.append("hyperlink_done")
                elif is_effectively_done:
                    tags.append("done")
                elif task.link:
                    tags.append("hyperlink")

            # 優先級顏色（保留，與字體 tag 一起使用）
            if task.priority == "high":
                tags.append("priority_high")
            elif task.priority == "low":
                tags.append("priority_low")

            # 搜尋標註
            if query and query in task.text.lower():
                tags.append("search_match")

            if tags:
                self.tree.item(item_id, tags=tuple(tags))
            
            # 遞迴處理子任務，傳遞當前的完成狀態
            if children:
                self._insert_tasks_recursive(children, task.id, is_effectively_done, query, use_wrapped)

    def _can_partial_update(self) -> bool:
        """目前的篩選/搜尋狀態是否允許跳過完整重繪。"""
        try:
            search_text = self.search_entry.get().strip()
            filter_mode = self.filter_var.get()
        except Exception:
            return False
        return not search_text and filter_mode == "all"

    def _compute_tags(self, task: Task, parent_is_done: bool, is_child: bool) -> Tuple[str, ...]:
        tags: List[str] = []
        is_effectively_done = task.is_done or parent_is_done
        if not is_child:
            if is_effectively_done and task.link:
                tags.append("parent_hyperlink_done")
            elif is_effectively_done:
                tags.append("parent_done")
            elif task.link:
                tags.append("parent_hyperlink")
            else:
                tags.append("parent")
        else:
            if is_effectively_done and task.link:
                tags.append("hyperlink_done")
            elif is_effectively_done:
                tags.append("done")
            elif task.link:
                tags.append("hyperlink")
        if task.priority == "high":
            tags.append("priority_high")
        elif task.priority == "low":
            tags.append("priority_low")
        return tuple(tags)

    def refresh_task(self, task_id: str) -> bool:
        """更新單一 tree item 的 values/tags，不重繪整棵樹。

        若無法部分更新（篩選/搜尋開啟、節點不存在），回傳 False 由呼叫端自行決定是否完整重繪。
        """
        if not self._can_partial_update():
            return False
        if not self.tree.exists(task_id):
            return False
        task = self.viewmodel.get_task_by_id(task_id)
        if task is None:
            return False
        parent_id = self.viewmodel._parent_index.get(task_id)
        parent_task = self.viewmodel.get_task_by_id(parent_id) if parent_id else None
        parent_is_done = bool(parent_task.is_done) if parent_task else False
        is_child = parent_id is not None

        priority_text = {"low": "低", "normal": "普通", "high": "高"}.get(task.priority, "普通")
        start_date_text = _format_short_date(task.start_date)
        due_date_text = _format_short_date(task.due_date)
        siblings = parent_task.children if parent_task else self.viewmodel.tasks
        try:
            index = siblings.index(task) + 1
        except ValueError:
            index = 1

        try:
            self.tree.item(
                task_id,
                text=f"{index}. {task.text}",
                values=(task.project or "", priority_text, start_date_text, due_date_text),
                tags=self._compute_tags(task, parent_is_done, is_child),
            )
        except Exception:
            _logger.exception("refresh_task 更新失敗：%s", task_id)
            return False
        return True

    def refresh_tasks(self, task_ids: List[str]) -> bool:
        """批次部分更新；任何一個失敗就回傳 False（呼叫端可回退到完整重繪）。"""
        if not task_ids:
            return True
        if not self._can_partial_update():
            return False
        for tid in task_ids:
            if not self.refresh_task(tid):
                return False
        return True

    def show_context_menu(self, event: Any) -> None:
        """在右鍵點擊時顯示上下文選單"""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            task_id = self.tree_item_to_task_id.get(item_id)
            if not task_id: return

            task, _ = self.viewmodel.find_task_by_id(task_id)
            if not task: return

            has_link = task.link is not None
            is_done = task.is_done

            done_label = "標示為未完成" if is_done else "標示為已完成"
            # 現在 index 0: 編輯, 1: 加入子項, 2: 標示為已完成/未完成
            self.context_menu.entryconfig(2, label=done_label)
            
            # 啟用/停用「開啟連結」與「移除連結」
            # 順序: 
            # 0: 編輯
            # 1: 加入子項
            # 2: 標示為已完成
            # 3: 刪除
            # 4: separator
            # 5: 開啟連結
            # 6: 移除連結
            try:
                self.context_menu.entryconfig(5, state="normal" if has_link else "disabled")
                self.context_menu.entryconfig(6, state="normal" if has_link else "disabled")
            except Exception:
                _logger.debug("以索引設定 context menu 失敗，回退到 label 比對", exc_info=True)
                for i in range(self.context_menu.index('end') + 1):
                    try:
                        label = self.context_menu.entrycget(i, 'label')
                        if label == '開啟連結' or label == '移除連結':
                            self.context_menu.entryconfig(i, state='normal' if has_link else 'disabled')
                    except Exception:
                        _logger.debug("設定 context menu 第 %s 項失敗", i, exc_info=True)
            self.context_menu.post(event.x_root, event.y_root)

    def open_link(self) -> None:
        """在右鍵選單點擊『開啟連結』時開啟瀏覽器連結（若存在）"""
        selected = self.tree.selection()
        if not selected:
            return

        item_id = selected[0]
        task_id = self.tree_item_to_task_id.get(item_id)
        if not task_id:
            task = self.viewmodel.get_task_by_id(item_id)
        else:
            task = self.viewmodel.get_task_by_id(task_id)

        if not task:
            return

        if task.link:
            try:
                webbrowser.open_new_tab(task.link)
                self.set_status(f"正在開啟連結: {task.link}")
            except Exception as e:
                self.set_status(f"無法開啟連結: {e}")
                messagebox.showerror("開啟連結失敗", f"無法開啟連結: {task.link}\n錯誤: {e}")

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "text":
            tree_item_id = self.tree.identify_row(event.y)
            if tree_item_id:
                task_id = self.tree_item_to_task_id.get(tree_item_id)
                task = self.viewmodel.get_task_by_id(task_id)
                if task and task.link:
                    try:
                        webbrowser.open_new_tab(task.link)
                        self.set_status(f"正在開啟連結: {task.link}")
                    except Exception as e:
                        self.set_status(f"無法開啟連結: {e}")
                        messagebox.showerror("開啟連結失敗", f"無法開啟連結: {task.link}\n錯誤: {e}")

    def on_b1_press(self, event):
        region = self.tree.identify_region(event.x, event.y)
        # 允許在 tree 或 text 區域開始拖曳，以便拖動包含文字的項目
        if region in ("tree", "text"):
            tree_item = self.tree.identify_row(event.y)
            if tree_item:
                # 設定初始拖曳資料，但尚未啟動實際拖動（等移動超過閾值）
                # 保存原始 tags，以便在取消或結束拖曳時恢復，避免清除字體樣式
                original_tags = tuple(self.tree.item(tree_item, "tags") or ())
                self.drag_data = {
                    "tree_item": tree_item,
                    "task_id": self.tree_item_to_task_id.get(tree_item),
                    "x": event.x,
                    "y": event.y,
                    "drag_started": False,
                    "original_tags": original_tags,
                }
    
    def on_b1_motion(self, event):
        if not self.drag_data.get("tree_item"):
            return

        # 計算與按下時的移動距離，只有超過閾值才視為真正開始拖曳
        dx = abs(event.x - self.drag_data.get("x", 0))
        dy = abs(event.y - self.drag_data.get("y", 0))
        if not self.drag_data.get("drag_started") and (dx >= self.drag_threshold or dy >= self.drag_threshold):
            self.drag_data["drag_started"] = True
            # 視覺提示：標示為 dragging
            try:
                self.tree.selection_set(self.drag_data["tree_item"])
                # 合併原始 tags 與暫時的 dragging tag，避免覆寫原有格式
                orig = tuple(self.drag_data.get("original_tags", ()))
                # 移除已存在的 dragging，然後加入一次
                new_tags = tuple([t for t in orig if t != "dragging"]) + ("dragging",)
                self.tree.item(self.drag_data["tree_item"], tags=new_tags)
                self.tree.tag_configure("dragging", background="lightblue")
            except Exception:
                _logger.debug("套用拖曳樣式失敗", exc_info=True)

        # 若已開始拖曳，可選擇顯示拖曳拖影或其他互動（目前保留最小視覺提示）

    def on_b1_release(self, event):
        # 若沒有 task_id 或 tree_item，直接清理
        if not self.drag_data.get("task_id"):
            if self.drag_data.get("tree_item"):
                try:
                    orig = self.drag_data.get("original_tags", ())
                    self.tree.item(self.drag_data.get("tree_item"), tags=orig)
                except Exception:
                    _logger.debug("還原拖曳樣式失敗", exc_info=True)
            self.drag_data = {}
            return

        if not self.drag_data.get("drag_started"):
            if self.drag_data.get("tree_item"):
                try:
                    orig = self.drag_data.get("original_tags", ())
                    self.tree.item(self.drag_data.get("tree_item"), tags=orig)
                except Exception:
                    _logger.debug("還原拖曳樣式失敗（短按）", exc_info=True)
            self.drag_data = {}
            return

        # 真正的拖放邏輯（只有在 drag_started 為 True 時執行）
        task_id_to_move = self.drag_data["task_id"]
        target_tree_item = self.tree.identify_row(event.y)
        target_task_id = self.tree_item_to_task_id.get(target_tree_item) if target_tree_item else None
        
        try:
            orig = self.drag_data.get("original_tags", ())
            self.tree.item(self.drag_data["tree_item"], tags=orig)
        except Exception:
            _logger.debug("還原拖曳樣式失敗（釋放）", exc_info=True)

        y = event.y
        bbox = self.tree.bbox(target_tree_item) if target_tree_item else None
        delta_x = event.x - self.drag_data["x"]

        command = MoveTaskCommand(self.viewmodel, task_id=task_id_to_move, target_id=target_task_id, y=y, bbox=bbox, delta_x=delta_x)
        self.viewmodel.execute_command(command)
        self.drag_data = {}

    def get_selected_task_ids(self) -> List[str]:
        selected_tree_items = self.tree.selection()
        return [self.tree_item_to_task_id[item] for item in selected_tree_items if item in self.tree_item_to_task_id]


    def show_edit_window(self, task: Task) -> None:
        editor_window = tk.Toplevel(self.root)
        editor_window.title("編輯任務")
        editor_window.geometry("450x300")
        editor_window.transient(self.root)
        editor_window.grab_set()

        tk.Label(editor_window, text="任務內容:", font=("Arial", 10)).pack(pady=(10,0), anchor="w", padx=10)
        text_entry = tk.Entry(editor_window, font=("Arial", 12))
        text_entry.pack(fill=tk.X, padx=10)
        text_entry.insert(0, task.text)

        tk.Label(editor_window, text="連結 (可選):", font=("Arial", 10)).pack(pady=(10,0), anchor="w", padx=10)
        link_entry = tk.Entry(editor_window, font=("Arial", 12))
        link_entry.pack(fill=tk.X, padx=10)
        if task.link:
            link_entry.insert(0, task.link)

        # 優先級選擇
        tk.Label(editor_window, text="優先級:", font=("Arial", 10)).pack(pady=(10,0), anchor="w", padx=10)
        priority_frame = tk.Frame(editor_window)
        priority_frame.pack(fill=tk.X, padx=10)
        priority_var = tk.StringVar(value=task.priority)
        for priority in ["低", "普通", "高"]:
            priority_value = {"低": "low", "普通": "normal", "高": "high"}[priority]
            tk.Radiobutton(priority_frame, text=priority, variable=priority_var, value=priority_value).pack(side=tk.LEFT)

        # 截止日期選擇
        tk.Label(editor_window, text="截止日期 (可選, 格式: YYYY-MM-DD):", font=("Arial", 10)).pack(pady=(10,0), anchor="w", padx=10)
        due_date_entry = tk.Entry(editor_window, font=("Arial", 12))
        due_date_entry.pack(fill=tk.X, padx=10)
        if task.due_date:
            due_date_entry.insert(0, task.due_date.isoformat())

        def save_and_close():
            new_text = text_entry.get().strip()
            new_link = link_entry.get().strip()
            new_priority = priority_var.get()
            due_date_str = due_date_entry.get().strip()
            
            if not new_text:
                messagebox.showwarning("輸入錯誤", "任務內容不可為空。", parent=editor_window)
                return
            
            # 解析截止日期
            new_due_date = None
            if due_date_str:
                try:
                    new_due_date = datetime.fromisoformat(due_date_str).date()
                except ValueError:
                    messagebox.showwarning("日期格式錯誤", "請使用 YYYY-MM-DD 格式。", parent=editor_window)
                    return
            
            command = UpdateTaskCommand(self.viewmodel, task_id=task.id, new_text=new_text, new_link=new_link, new_priority=new_priority, new_due_date=new_due_date)
            self.viewmodel.execute_command(command)
            editor_window.destroy()

        button_frame = tk.Frame(editor_window)
        button_frame.pack(pady=10)
        save_button = tk.Button(button_frame, text="儲存", command=save_and_close)
        save_button.pack(side=tk.LEFT, padx=5)
        cancel_button = tk.Button(button_frame, text="取消", command=editor_window.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)

        self.root.wait_window(editor_window)

    def apply_filter(self) -> None:
        """應用搜尋和篩選條件"""
        self.redraw_tree()
        
        # 更新狀態列
        search_text = self.search_entry.get()
        filter_mode = self.filter_var.get()
        
        filter_names = {
            "all": "全部",
            "incomplete": "未完成",
            "high_priority": "高優先",
            "completed": "已完成"
        }
        
        if search_text:
            self.set_status(f"搜尋: '{search_text}' | 篩選: {filter_names.get(filter_mode, '全部')}")
        else:
            self.set_status(f"篩選: {filter_names.get(filter_mode, '全部')}")

    def update_undo_redo_buttons(self) -> None:
        """更新 Undo/Redo 按鈕的狀態"""
        if getattr(self.viewmodel, 'history', None) and self.viewmodel.history.can_undo():
            self.undo_button.config(state="normal")
        else:
            self.undo_button.config(state="disabled")
        
        if getattr(self.viewmodel, 'history', None) and self.viewmodel.history.can_redo():
            self.redo_button.config(state="normal")
        else:
            self.redo_button.config(state="disabled")

    def on_tree_open(self, event: Any) -> None:
        """當 Treeview 節點展開時，確保子節點繼承正確的完成樣式"""
        parent_id = self.tree.focus()
        if not parent_id:
            return

        parent_task = self.viewmodel.get_task_by_id(parent_id)
        if not parent_task:
            return

        # 檢查父節點是否應該被視為已完成或為父項粗體樣式
        parent_tags = set(self.tree.item(parent_id, "tags") or ())
        parent_is_effectively_done = parent_task.is_done or any(t in parent_tags for t in ("done", "hyperlink_done", "parent_done", "parent_hyperlink_done"))
        parent_is_parent_style = any(t.startswith("parent") for t in parent_tags)

        for child_id in self.tree.get_children(parent_id):
            child_task = self.viewmodel.get_task_by_id(child_id)
            if not child_task:
                continue

            # 重新建立子項的 tags：不包含任何 parent_*（粗體）標籤
            new_tags = [t for t in (self.tree.item(child_id, "tags") or ()) if t not in ("parent", "parent_done", "parent_hyperlink", "parent_hyperlink_done")]

            # 子項是否應視為已完成：若父項為已完成，也可視為已完成（保留原有行為）
            child_effectively_done = child_task.is_done or parent_is_effectively_done

            # 根據是否有連結與完成狀態，套用非粗體的完成/連結樣式
            # 先移除舊的完成/連結樣式
            new_tags = [t for t in new_tags if t not in ("done", "hyperlink_done", "hyperlink")]

            if child_task.link and child_effectively_done:
                new_tags.append("hyperlink_done")
            elif child_effectively_done:
                new_tags.append("done")
            elif child_task.link:
                new_tags.append("hyperlink")

            # 保留優先級顏色等非父/完成/連結標籤
            for t in (self.tree.item(child_id, "tags") or ()): 
                if t in ("priority_high", "priority_low") and t not in new_tags:
                    new_tags.append(t)

            self.tree.item(child_id, tags=tuple(new_tags))
