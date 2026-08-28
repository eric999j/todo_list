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

# --- UI 通用字體 ---
UI_FONT = "Segoe UI"


def _format_short_date(value: Any) -> str:
    """將 date/datetime/str 轉為 'MM/DD' 顯示字串；跨年時附加年份。"""
    if not value:
        return ""
    d = _coerce_date(value)
    if d is None:
        return str(value)
    today = date.today()
    if d.year != today.year:
        return d.strftime("%Y/%m/%d")
    return d.strftime("%m/%d")


def _coerce_date(value: Any) -> Optional[date]:
    """將 date/datetime/str 統一轉為 date；失敗時回傳 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.fromisoformat(value).date()
            except (ValueError, TypeError):
                return None
    return None


def _due_state(due: Any, is_done: bool) -> str:
    """回傳截止日狀態：'overdue'（逾期）、'due_today'（今日）、'due_soon'（3 天內）、''。"""
    if is_done:
        return ""
    d = _coerce_date(due)
    if d is None:
        return ""
    today = date.today()
    if d < today:
        return "overdue"
    if d == today:
        return "due_today"
    if (d - today).days <= 3:
        return "due_soon"
    return ""


def _real_text(entry: tk.Entry) -> str:
    """讀取 Entry 實際內容；若目前是 placeholder 狀態則回空字串。"""
    if getattr(entry, "_is_placeholder", False):
        return ""
    return entry.get()


def _install_placeholder(entry: tk.Entry, text: str, placeholder_color: str, normal_color: str) -> None:
    """為 Entry 掛上 placeholder 行為；透過 _real_text() 讀取真實值。"""
    entry._placeholder_text = text
    entry._placeholder_color = placeholder_color
    entry._normal_color = normal_color

    def _apply_placeholder():
        entry.delete(0, tk.END)
        entry.insert(0, text)
        entry.config(fg=placeholder_color)
        entry._is_placeholder = True

    def _on_focus_in(_=None):
        if getattr(entry, "_is_placeholder", False):
            entry.delete(0, tk.END)
            entry.config(fg=normal_color)
            entry._is_placeholder = False

    def _on_focus_out(_=None):
        if not entry.get():
            _apply_placeholder()

    entry.bind("<FocusIn>", _on_focus_in, add="+")
    entry.bind("<FocusOut>", _on_focus_out, add="+")
    _apply_placeholder()


def _refresh_placeholder_colors(entry: tk.Entry, placeholder_color: str, normal_color: str) -> None:
    """主題切換時重新套用 placeholder / 正常文字顏色。"""
    entry._placeholder_color = placeholder_color
    entry._normal_color = normal_color
    if getattr(entry, "_is_placeholder", False):
        entry.config(fg=placeholder_color)
    else:
        entry.config(fg=normal_color)


def _center_window(win: tk.Toplevel, parent: Optional[tk.Misc] = None) -> None:
    """將 Toplevel 置中於父視窗（或螢幕）。"""
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        if parent is not None and parent.winfo_viewable():
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 3
        else:
            x = (win.winfo_screenwidth() - w) // 2
            y = (win.winfo_screenheight() - h) // 3
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        _logger.debug("置中對話框失敗", exc_info=True)


class _Tooltip:
    """輕量 Tooltip：滑鼠停留一段時間後顯示提示。"""

    def __init__(self, widget: tk.Misc, text: str, delay: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set_text(self, text: str) -> None:
        self.text = text

    def _schedule(self, _event: Any = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tw,
                text=self.text,
                bg="#2b2b2b",
                fg="#ffffff",
                relief="solid",
                bd=0,
                padx=8,
                pady=4,
                font=(UI_FONT, 9),
            ).pack()
            self._tip = tw
        except Exception:
            _logger.debug("顯示 tooltip 失敗", exc_info=True)

    def _hide(self, _event: Any = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

class UIManager:
    """負責建立和管理 UI 元件及事件綁定"""

    THEMES = {
        "light": {
            "bg": "#ffffff", "fg": "#333333",
            "frame_bg": "#f5f7fa",
            "entry_bg": "#ffffff", "entry_fg": "#333333",
            "tree_bg": "#ffffff", "tree_fg": "#333333", "tree_field": "#ffffff", "tree_sel": "#e1f0fa",
            "row_alt": "#fafbfc",
            "button_bg": "#eaecef", "button_fg": "#333333",
            "highlight": "#0078d4",
            "status_bg": "#f5f7fa", "status_fg": "#555555",
            "placeholder": "#a0a0a0",
            "muted": "#888888",
            "danger": "#d13438",
            "warning": "#c67c00",
            "success": "#107c10",
            "drop_target": "#cfe8ff",
            "border": "#d0d7de",
        },
        "dark": {
            "bg": "#1e1e1e", "fg": "#e0e0e0",
            "frame_bg": "#252526",
            "entry_bg": "#3c3c3c", "entry_fg": "#ffffff",
            "tree_bg": "#252526", "tree_fg": "#cccccc", "tree_field": "#252526", "tree_sel": "#37373d",
            "row_alt": "#2a2a2b",
            "button_bg": "#333333", "button_fg": "#cccccc",
            "highlight": "#0a84ff",
            "status_bg": "#252526", "status_fg": "#d4d4d4",
            "placeholder": "#6d6d6d",
            "muted": "#9a9a9a",
            "danger": "#ff6b6b",
            "warning": "#f2a15b",
            "success": "#4ec97a",
            "drop_target": "#264f78",
            "border": "#3c3c3c",
        }
    }

    def __init__(self, root: tk.Tk, viewmodel: Any) -> None:
        self.root: tk.Tk = root
        self.viewmodel: Any = viewmodel # UI 持有 VM，但不直接改資料
        self.tree_item_to_task_id: Dict[str, str] = {}
        self.drag_data: Dict[str, Any] = {}
        self.current_filter: str = "all"
        self.search_query: str = ""

        # 搜尋 debounce 與拖曳 hover
        self._search_after_id: Optional[str] = None
        self._drop_target_id: Optional[str] = None
        self._tooltips: List[_Tooltip] = []

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
        # 視窗最小尺寸，避免版面破碎
        try:
            self.root.minsize(720, 480)
        except Exception:
            _logger.debug("設定最小視窗尺寸失敗", exc_info=True)

        # Configure Grid Weight for Root
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1) # The treeview row

        theme = self.theme

        # --- Header Frame (Search, Filter, Undo/Redo) ---
        self.header_frame = tk.Frame(self.root)
        self.header_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)

        # Search Frame inside Header
        search_filter_frame = tk.Frame(self.header_frame)
        search_filter_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # 搜尋框（含清除按鈕）
        tk.Label(search_filter_frame, text="🔍", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=(0, 5))
        search_box = tk.Frame(search_filter_frame, bd=1, relief="solid")
        search_box.pack(side=tk.LEFT)
        self.search_entry = tk.Entry(
            search_box, width=28, font=(UI_FONT, 10), relief="flat", bd=0
        )
        self.search_entry.pack(side=tk.LEFT, padx=(6, 0), ipady=3)
        _install_placeholder(
            self.search_entry,
            "搜尋任務內容…",
            theme["placeholder"],
            theme["entry_fg"],
        )
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.clear_search_btn = tk.Button(
            search_box,
            text="✕",
            command=self._clear_search,
            font=(UI_FONT, 8),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=6,
        )
        self.clear_search_btn.pack(side=tk.LEFT)
        self._search_box_frame = search_box
        # 初始隱藏清除鈕
        self._update_clear_search_visibility()

        # 篩選按鈕
        tk.Label(search_filter_frame, text=" | 篩選:", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=(15, 5))

        self.filter_var = tk.StringVar(value="all")
        filters = [
            ("全部", "all"),
            ("未完成", "incomplete"),
            ("高優先", "high_priority"),
            ("已完成", "completed"),
        ]

        self.filter_radios = []
        for text, value in filters:
            rb = tk.Radiobutton(
                search_filter_frame,
                text=text,
                variable=self.filter_var,
                value=value,
                command=self.apply_filter,
                font=(UI_FONT, 9),
                indicatoron=0,
                width=8,
                padx=5,
                pady=3,
                relief="flat",
                bd=0,
                cursor="hand2",
            )
            rb.pack(side=tk.LEFT, padx=2)
            self.filter_radios.append(rb)

        # 復原/重做按鈕
        undo_redo_frame = tk.Frame(search_filter_frame)
        undo_redo_frame.pack(side=tk.RIGHT)

        self.undo_button = tk.Button(
            undo_redo_frame, text="↶", command=self.viewmodel.undo,
            font=("Segoe UI Symbol", 12), state="disabled", width=3, relief="flat", cursor="hand2",
        )
        self.undo_button.pack(side=tk.LEFT, padx=2)

        self.redo_button = tk.Button(
            undo_redo_frame, text="↷", command=self.viewmodel.redo,
            font=("Segoe UI Symbol", 12), state="disabled", width=3, relief="flat", cursor="hand2",
        )
        self.redo_button.pack(side=tk.LEFT, padx=2)

        self._tooltips.append(_Tooltip(self.undo_button, "復原 (Ctrl+Z)"))
        self._tooltips.append(_Tooltip(self.redo_button, "重做 (Ctrl+Y)"))
        self._tooltips.append(_Tooltip(self.clear_search_btn, "清除搜尋 (Esc)"))

        # --- Input Frame (Add, Export) ---
        self.input_frame = tk.Frame(self.root)
        self.input_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 6))

        self.entry = tk.Entry(self.input_frame, font=(UI_FONT, 11), relief="solid", bd=1)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=4)
        self.entry.bind("<Return>", lambda e: self.add_task())
        _install_placeholder(
            self.entry,
            "輸入新任務後按 Enter 或點『新增』…",
            theme["placeholder"],
            theme["entry_fg"],
        )

        # Clean buttons
        self.add_button = tk.Button(
            self.input_frame, text="➕ 新增", command=self.add_task,
            font=(UI_FONT, 10, "bold"), relief="flat", padx=14, pady=2,
            bg=theme["highlight"], fg="#ffffff", cursor="hand2",
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )
        self.add_button.pack(side=tk.LEFT, padx=2)

        self.export_button = tk.Button(
            self.input_frame, text="📤 匯出", command=self.export_markdown,
            font=(UI_FONT, 9), relief="flat", padx=10, cursor="hand2",
        )
        self.export_button.pack(side=tk.LEFT, padx=2)

        self.expand_button = tk.Button(
            self.input_frame, text="⊞", command=self._expand_all,
            font=(UI_FONT, 10), relief="flat", padx=8, cursor="hand2", width=2,
        )
        self.expand_button.pack(side=tk.LEFT, padx=(6, 0))

        self.collapse_button = tk.Button(
            self.input_frame, text="⊟", command=self._collapse_all,
            font=(UI_FONT, 10), relief="flat", padx=8, cursor="hand2", width=2,
        )
        self.collapse_button.pack(side=tk.LEFT, padx=(2, 0))

        self._tooltips.append(_Tooltip(self.add_button, "新增任務 (Ctrl+N)"))
        self._tooltips.append(_Tooltip(self.export_button, "匯出成 Markdown"))
        self._tooltips.append(_Tooltip(self.expand_button, "全部展開"))
        self._tooltips.append(_Tooltip(self.collapse_button, "全部摺疊"))

        # --- Help/Hint Label ---
        help_text = "💡 Ctrl+N 新增｜Ctrl+F 搜尋｜F2 編輯｜Space 完成｜Del 刪除｜Ctrl+Z 復原"
        self.help_label = tk.Label(self.root, text=help_text, font=(UI_FONT, 9), anchor="w")
        self.help_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 4))

        # --- Treeview Frame ---
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=0)
        self._tree_frame = tree_frame

        # Treeview Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Treeview 多欄顯示
        columns = ("project", "priority", "start_date", "due_date")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            selectmode="extended",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.tree.yview)

        # 設定欄位標題
        self.tree.heading("#0", text=" 項目內容")
        self.tree.heading("project", text="專案")
        self.tree.heading("priority", text="優先級")
        self.tree.heading("start_date", text="開始")
        self.tree.heading("due_date", text="截止")

        # 設定欄寬
        self.tree.column("#0", width=420, minwidth=220)
        self.tree.column("project", width=110, minwidth=80, anchor="center")
        self.tree.column("priority", width=70, minwidth=50, anchor="center")
        self.tree.column("start_date", width=80, minwidth=70, anchor="center")
        self.tree.column("due_date", width=80, minwidth=70, anchor="center")

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 空狀態畫面 (置於 tree 之上，用 place 覆蓋)
        self.empty_state_label = tk.Label(
            tree_frame,
            text="🗒  尚無任務\n\n在上方輸入內容後按 Enter，開始建立第一項待辦。",
            font=(UI_FONT, 11),
            justify="center",
            anchor="center",
        )

        # Treeview Tags Styling
        self._configure_tree_tags()

        # --- Bottom Bar (Status & Stats & Theme Toggle) ---
        self.bottom_bar = tk.Frame(self.root, height=30)
        self.bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Status Label (左：訊息)
        self.status_label = tk.Label(
            self.bottom_bar, text="就緒", anchor=tk.W, font=(UI_FONT, 9), padx=10
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Stats Label (中：任務統計)
        self.stats_label = tk.Label(
            self.bottom_bar, text="", anchor=tk.E, font=(UI_FONT, 9), padx=10
        )
        self.stats_label.pack(side=tk.LEFT)

        # Theme Toggle Button (Bottom Right)
        self.theme_toggle_btn = tk.Button(
            self.bottom_bar,
            text="🌙" if not self.is_dark_mode else "☀️",
            command=self.toggle_theme,
            font=(UI_FONT, 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=8,
        )
        self.theme_toggle_btn.pack(side=tk.RIGHT, padx=6, pady=2)
        self._tooltips.append(_Tooltip(self.theme_toggle_btn, "切換淺色/深色主題"))

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
        default_font_name = UI_FONT
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

        # 8. 到期樣式（背景色，由 apply_theme 動態覆寫顏色）
        self.tree.tag_configure("overdue", background="#ffe1e1")
        self.tree.tag_configure("due_today", background="#fff4c9")
        self.tree.tag_configure("due_soon", background="#fff9df")

        # 9. Zebra strip（列交錯）與拖曳 drop target
        self.tree.tag_configure("drop_target", background="#cfe8ff")

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

        # 2. Header 內元件
        for widget in self.header_frame.winfo_children():
            try:
                widget.configure(bg=theme["frame_bg"])
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=theme["frame_bg"], fg=theme["fg"])
                elif isinstance(child, tk.Frame):
                    child.configure(bg=theme["frame_bg"])
                    # 搜尋框容器
                    for grand in child.winfo_children():
                        if isinstance(grand, tk.Entry):
                            grand.configure(
                                bg=theme["entry_bg"],
                                insertbackground=theme["fg"],
                                highlightthickness=0,
                                bd=0,
                            )
                            _refresh_placeholder_colors(
                                grand, theme["placeholder"], theme["entry_fg"]
                            )
                        elif isinstance(grand, tk.Button):
                            grand.configure(
                                bg=theme["entry_bg"],
                                fg=theme["muted"],
                                activebackground=theme["entry_bg"],
                                activeforeground=theme["fg"],
                            )
        # 搜尋框外框顏色
        try:
            self._search_box_frame.configure(bg=theme["entry_bg"], highlightthickness=0)
        except Exception:
            _logger.debug("套用搜尋框主題失敗", exc_info=True)

        # Filter Radios
        selected_bg = theme["highlight"]
        unselected_bg = theme["button_bg"]
        for rb in self.filter_radios:
            rb.configure(
                bg=unselected_bg,
                fg=theme["button_fg"],
                activebackground=theme["highlight"],
                activeforeground="#ffffff",
                selectcolor=selected_bg,
                highlightthickness=0,
            )

        # Undo/Redo Buttons
        for btn in [self.undo_button, self.redo_button]:
            btn.configure(
                bg=theme["button_bg"], fg=theme["button_fg"],
                activebackground=theme["highlight"], activeforeground="#ffffff",
                highlightthickness=0,
            )

        # Input Frame
        self.help_label.configure(bg=theme["bg"], fg=theme["muted"])
        self.entry.configure(
            bg=theme["entry_bg"], fg=theme["entry_fg"],
            insertbackground=theme["fg"],
            highlightthickness=0,
        )
        _refresh_placeholder_colors(self.entry, theme["placeholder"], theme["entry_fg"])

        self.input_frame.configure(bg=theme["bg"])
        self.add_button.configure(
            bg=theme["highlight"], fg="#ffffff",
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )
        self.export_button.configure(
            bg=theme["button_bg"], fg=theme["button_fg"],
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )
        self.expand_button.configure(
            bg=theme["button_bg"], fg=theme["button_fg"],
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )
        self.collapse_button.configure(
            bg=theme["button_bg"], fg=theme["button_fg"],
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )

        # Tree frame 背景
        try:
            self._tree_frame.configure(bg=theme["bg"])
        except Exception:
            _logger.debug("套用 tree_frame 主題失敗", exc_info=True)

        # 空狀態
        self.empty_state_label.configure(bg=theme["tree_bg"], fg=theme["muted"])

        # Bottom Bar
        self.bottom_bar.configure(bg=theme["status_bg"])
        self.status_label.configure(bg=theme["status_bg"], fg=theme["status_fg"])
        self.stats_label.configure(bg=theme["status_bg"], fg=theme["muted"])
        self.theme_toggle_btn.configure(
            bg=theme["status_bg"], fg=theme["status_fg"],
            activebackground=theme["highlight"], activeforeground="#ffffff",
        )
        self.theme_toggle_btn.config(text="🌙" if not self.is_dark_mode else "☀️")

        # Treeview Styles (using ttk.Style)
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Treeview",
            background=theme["tree_bg"],
            foreground=theme["tree_fg"],
            fieldbackground=theme["tree_field"],
            font=(UI_FONT, 10),
            rowheight=26,
            borderwidth=0,
        )
        style.map("Treeview",
            background=[('selected', theme["highlight"])],
            foreground=[('selected', '#ffffff')],
        )
        style.configure("Treeview.Heading",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
            relief="flat",
            font=(UI_FONT, 10, "bold"),
        )
        style.map("Treeview.Heading",
            background=[('active', theme["highlight"])],
            foreground=[('active', '#ffffff')],
        )

        # 顏色重新設定
        link_color = "#5ea9ff" if mode == "dark" else "#0064d0"
        self.tree.tag_configure("hyperlink", foreground=link_color)
        self.tree.tag_configure("hyperlink_done", foreground=link_color)
        self.tree.tag_configure("parent_hyperlink", foreground=link_color)
        self.tree.tag_configure("parent_hyperlink_done", foreground=link_color)

        priority_high = theme["danger"]
        priority_low = theme["success"]
        self.tree.tag_configure("priority_high", foreground=priority_high)
        self.tree.tag_configure("priority_low", foreground=priority_low)

        # 搜尋結果標註
        search_match_bg = "#5a5a1f" if mode == "dark" else "#fff2cc"
        self.tree.tag_configure("search_match", background=search_match_bg)

        # 到期樣式（背景）
        overdue_bg = "#5c2a2a" if mode == "dark" else "#ffe1e1"
        due_today_bg = "#5c4b1f" if mode == "dark" else "#fff4c9"
        due_soon_bg = "#4a4426" if mode == "dark" else "#fff9df"
        self.tree.tag_configure("overdue", background=overdue_bg)
        self.tree.tag_configure("due_today", background=due_today_bg)
        self.tree.tag_configure("due_soon", background=due_soon_bg)

        # Zebra 與 drop target
        self.tree.tag_configure("drop_target", background=theme["drop_target"])


    def on_search_change(self, event: Any) -> None:
        """當搜尋框內容改變時觸發"""
        self.search_query = _real_text(self.search_entry)
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
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="日期格式: YYYY-MM-DD", font=(UI_FONT, 9)).pack(anchor=tk.W)

        date_entry = tk.Entry(frame, font=(UI_FONT, 11), width=20)
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

        tk.Button(
            button_frame, text="確定", command=save_date, width=8,
            font=(UI_FONT, 10, "bold"), relief="flat",
            bg=self.theme["highlight"], fg="#ffffff", cursor="hand2",
            activebackground=self.theme["highlight"], activeforeground="#ffffff",
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame, text="取消", command=dialog.destroy, width=8,
            font=(UI_FONT, 10), relief="flat", cursor="hand2",
        ).pack(side=tk.LEFT)

        self._apply_dialog_theme(dialog)
        _center_window(dialog, self.root)

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

        # 全域鍵盤快捷鍵
        self.root.bind("<Control-z>", lambda event: self.viewmodel.undo())
        self.root.bind("<Control-Z>", lambda event: self.viewmodel.undo())
        self.root.bind("<Control-y>", lambda event: self.viewmodel.redo())
        self.root.bind("<Control-Y>", lambda event: self.viewmodel.redo())
        self.root.bind("<Control-n>", self._focus_add_entry)
        self.root.bind("<Control-N>", self._focus_add_entry)
        self.root.bind("<Control-f>", self._focus_search_entry)
        self.root.bind("<Control-F>", self._focus_search_entry)
        self.root.bind("<Escape>", self._on_escape)

        # Tree 專用快捷鍵
        self.tree.bind("<F2>", lambda e: self.edit_task())
        self.tree.bind("<space>", self._on_space_toggle)
        self.tree.bind("<Return>", lambda e: self.edit_task())

    # --- UX helpers (placeholder / search / statistics / empty state) ---

    def _on_search_key(self, event: Any) -> None:
        """搜尋框按鍵：debounce 觸發重繪。"""
        self._update_clear_search_visibility()
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.root.after(180, self._run_search)

    def _run_search(self) -> None:
        self._search_after_id = None
        self.apply_filter()

    def _clear_search(self) -> None:
        """清除搜尋內容並回到未搜尋狀態。"""
        try:
            self.search_entry.focus_set()
            self.search_entry.delete(0, tk.END)
            # 觸發 focus_out 讓 placeholder 還原
            self.tree.focus_set()
        except Exception:
            _logger.debug("清除搜尋失敗", exc_info=True)
        self._update_clear_search_visibility()
        self.apply_filter()

    def _update_clear_search_visibility(self) -> None:
        """有內容時顯示 ✕ 清除按鈕，否則隱藏（透過 config）。"""
        try:
            has_text = bool(_real_text(self.search_entry).strip())
            if has_text:
                self.clear_search_btn.config(state="normal")
            else:
                self.clear_search_btn.config(state="disabled")
        except Exception:
            _logger.debug("更新清除鈕狀態失敗", exc_info=True)

    def _update_statistics(self) -> None:
        """更新底部任務統計。"""
        total, done = self._count_tasks(self.viewmodel.tasks)
        pending = total - done
        if total == 0:
            self.stats_label.config(text="")
        else:
            self.stats_label.config(text=f"共 {total} 項 ｜ 待辦 {pending} ｜ 完成 {done}")

    def _count_tasks(self, tasks: List[Task]) -> Tuple[int, int]:
        total = 0
        done = 0
        for t in tasks:
            total += 1
            if t.is_done:
                done += 1
            sub_total, sub_done = self._count_tasks(t.children)
            total += sub_total
            done += sub_done
        return total, done

    # --- Dialog helpers ---

    def _apply_dialog_theme(self, dialog: tk.Toplevel) -> None:
        """對話框套用當前主題（背景、Label、Entry、Radiobutton、Button）。"""
        theme = self.theme
        try:
            dialog.configure(bg=theme["bg"])
            for w in dialog.winfo_children():
                self._theme_widget_recursive(w, theme)
        except Exception:
            _logger.debug("套用對話框主題失敗", exc_info=True)

    def _theme_widget_recursive(self, widget: tk.Misc, theme: Dict[str, str]) -> None:
        cls = widget.winfo_class()
        try:
            if cls in ("Frame", "Labelframe"):
                widget.configure(bg=theme["bg"])
            elif cls == "Label":
                widget.configure(bg=theme["bg"], fg=theme["fg"])
            elif cls == "Entry":
                widget.configure(
                    bg=theme["entry_bg"], fg=theme["entry_fg"],
                    insertbackground=theme["fg"],
                    highlightthickness=0, relief="solid", bd=1,
                )
            elif cls == "Radiobutton":
                widget.configure(
                    bg=theme["bg"], fg=theme["fg"],
                    activebackground=theme["bg"], activeforeground=theme["fg"],
                    selectcolor=theme["bg"],
                )
            elif cls == "Button":
                # 保留已有 background（主要按鈕）
                current_bg = widget.cget("bg")
                if current_bg in ("SystemButtonFace", "", None):
                    widget.configure(
                        bg=theme["button_bg"], fg=theme["button_fg"],
                        activebackground=theme["highlight"], activeforeground="#ffffff",
                    )
        except Exception:
            _logger.debug("套用單一元件主題失敗 (%s)", cls, exc_info=True)
        for child in widget.winfo_children():
            self._theme_widget_recursive(child, theme)

    def _update_empty_state(self) -> None:
        """依 tree 是否有項目，顯示或隱藏空狀態畫面。"""
        try:
            has_children = bool(self.tree.get_children(""))
        except Exception:
            has_children = True

        try:
            if has_children:
                self.empty_state_label.place_forget()
            else:
                # 依搜尋/篩選調整訊息
                search_txt = _real_text(self.search_entry).strip()
                filter_mode = self.filter_var.get()
                if search_txt or filter_mode != "all":
                    self.empty_state_label.config(
                        text=f"🔍  沒有符合條件的任務\n\n嘗試清除搜尋或切換篩選為「全部」。"
                    )
                else:
                    self.empty_state_label.config(
                        text="🗒  尚無任務\n\n在上方輸入內容後按 Enter，開始建立第一項待辦。"
                    )
                self.empty_state_label.place(relx=0.5, rely=0.45, anchor="center")
        except Exception:
            _logger.debug("更新空狀態失敗", exc_info=True)

    def _expand_all(self) -> None:
        """全部展開節點。"""
        try:
            def _walk(iid: str) -> None:
                for c in self.tree.get_children(iid):
                    self.tree.item(c, open=True)
                    _walk(c)
            _walk("")
        except Exception:
            _logger.debug("全部展開失敗", exc_info=True)

    def _collapse_all(self) -> None:
        """全部摺疊節點。"""
        try:
            def _walk(iid: str) -> None:
                for c in self.tree.get_children(iid):
                    _walk(c)
                    self.tree.item(c, open=False)
            _walk("")
        except Exception:
            _logger.debug("全部摺疊失敗", exc_info=True)

    def _focus_add_entry(self, event: Any = None) -> str:
        try:
            self.entry.focus_set()
            self.entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    def _focus_search_entry(self, event: Any = None) -> str:
        try:
            self.search_entry.focus_set()
            self.search_entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    def _on_escape(self, event: Any = None) -> None:
        """Escape：清除搜尋 → 若已空，將焦點移到 tree。"""
        try:
            focused = self.root.focus_get()
            if focused is self.search_entry or _real_text(self.search_entry).strip():
                self._clear_search()
            else:
                self.tree.focus_set()
        except Exception:
            _logger.debug("Escape 處理失敗", exc_info=True)

    def _on_space_toggle(self, event: Any) -> str:
        """Tree 上按空白鍵：切換完成狀態。"""
        try:
            sel = self.tree.selection()
            if not sel:
                return "break"
            from commands.task_commands import ToggleDoneStatusCommand
            task_ids = [self.tree_item_to_task_id.get(i, i) for i in sel]
            cmd = ToggleDoneStatusCommand(self.viewmodel, task_ids=task_ids)
            self.viewmodel.execute_command(cmd)
        except Exception:
            _logger.exception("Space 切換完成狀態失敗")
        return "break"

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
        text = _real_text(self.entry).strip()
        if text:
            command = AddTaskCommand(self.viewmodel, task_text=text)
            self.viewmodel.execute_command(command) # 將變更委派給 ViewModel
            self.entry.delete(0, tk.END)
            # 觸發 placeholder 復原
            self.root.focus_set()
            self.entry.focus_set()
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
        edit_window.geometry("420x560")
        edit_window.transient(self.root)
        edit_window.grab_set()

        # 專案名稱
        tk.Label(edit_window, text="專案名稱:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        project_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        project_entry.insert(0, task.project or "")
        project_entry.pack(pady=5, ipady=3)

        # 任務內容
        tk.Label(edit_window, text="任務內容:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        text_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        text_entry.insert(0, task.text)
        text_entry.pack(pady=5, ipady=3)

        # 優先級
        tk.Label(edit_window, text="優先級:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        priority_var = tk.StringVar(value=task.priority)
        priority_frame = tk.Frame(edit_window)
        priority_frame.pack(pady=5)

        tk.Radiobutton(priority_frame, text="低", variable=priority_var, value="low", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(priority_frame, text="普通", variable=priority_var, value="normal", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(priority_frame, text="高", variable=priority_var, value="high", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)

        date_values = ["今天", "明天", "下週"]

        # 開始日期
        tk.Label(edit_window, text="開始日期:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        # 預設為建立日期，但若 task 已經有 start_date 則使用之
        current_start_date = str(task.start_date) if task.start_date else (str(task.creation_time.date()) if task.creation_time else "")
        start_date_values = date_values.copy()
        if current_start_date and current_start_date not in start_date_values:
            start_date_values.append(current_start_date)
        start_date_combo = ttk.Combobox(edit_window, values=start_date_values, width=37, font=(UI_FONT, 11))
        start_date_combo.pack(pady=5)
        if current_start_date:
            start_date_combo.set(current_start_date)

        # 截止日期 (改為 Combobox)
        tk.Label(edit_window, text="截止日期:", font=(UI_FONT, 10)).pack(pady=(10, 5))

        current_date_val = str(task.due_date) if task.due_date else ""
        due_date_values = date_values.copy()
        if current_date_val and current_date_val not in due_date_values:
            due_date_values.append(current_date_val)

        due_date_combo = ttk.Combobox(edit_window, values=due_date_values, width=37, font=(UI_FONT, 11))
        due_date_combo.pack(pady=5)
        if current_date_val:
            due_date_combo.set(current_date_val)

        # 狀態 (已完成/未完成)
        tk.Label(edit_window, text="狀態:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        status_frame = tk.Frame(edit_window)
        status_frame.pack(pady=5)
        status_var = tk.BooleanVar(value=task.is_done)

        tk.Radiobutton(status_frame, text="未完成", variable=status_var, value=False, font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(status_frame, text="已完成", variable=status_var, value=True, font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)

        # 超連結
        tk.Label(edit_window, text="超連結 (URL):", font=(UI_FONT, 10)).pack(pady=(10, 5))
        link_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        link_entry.insert(0, task.link or "")
        link_entry.pack(pady=5, ipady=3)
        
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

        save_btn = tk.Button(
            button_frame, text="儲存", command=save_changes,
            font=(UI_FONT, 10, "bold"), width=10, relief="flat",
            bg=self.theme["highlight"], fg="#ffffff", cursor="hand2",
            activebackground=self.theme["highlight"], activeforeground="#ffffff",
        )
        save_btn.pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame, text="取消", command=edit_window.destroy,
            font=(UI_FONT, 10), width=10, relief="flat", cursor="hand2",
        ).pack(side=tk.LEFT, padx=5)

        self._apply_dialog_theme(edit_window)
        _center_window(edit_window, self.root)

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
        edit_window.geometry("420x560")
        edit_window.transient(self.root)
        edit_window.grab_set()

        # 專案名稱
        tk.Label(edit_window, text="專案名稱:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        project_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        if parent_task.project:
            project_entry.insert(0, parent_task.project)
        project_entry.pack(pady=5, ipady=3)

        # 任務內容
        tk.Label(edit_window, text="任務內容:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        text_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        text_entry.pack(pady=5, ipady=3)
        text_entry.focus_set()

        # 優先級
        tk.Label(edit_window, text="優先級:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        priority_var = tk.StringVar(value="normal")
        priority_frame = tk.Frame(edit_window)
        priority_frame.pack(pady=5)

        tk.Radiobutton(priority_frame, text="低", variable=priority_var, value="low", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(priority_frame, text="普通", variable=priority_var, value="normal", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)
        tk.Radiobutton(priority_frame, text="高", variable=priority_var, value="high", font=(UI_FONT, 10)).pack(side=tk.LEFT, padx=6)

        date_values = ["今天", "明天", "下週"]

        # 開始日期 (Default to today)
        tk.Label(edit_window, text="開始日期:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        from datetime import datetime
        current_start_date = str(datetime.now().date())
        start_date_values = date_values.copy()
        if current_start_date not in start_date_values:
            start_date_values.append(current_start_date)
        start_date_combo = ttk.Combobox(edit_window, values=start_date_values, width=37, font=(UI_FONT, 11))
        start_date_combo.pack(pady=5)
        if current_start_date:
            start_date_combo.set(current_start_date)

        # 截止日期
        tk.Label(edit_window, text="截止日期:", font=(UI_FONT, 10)).pack(pady=(10, 5))
        due_date_combo = ttk.Combobox(edit_window, values=date_values, width=37, font=(UI_FONT, 11))
        due_date_combo.pack(pady=5)

        # 超連結
        tk.Label(edit_window, text="超連結 (URL):", font=(UI_FONT, 10)).pack(pady=(10, 5))
        link_entry = tk.Entry(edit_window, width=40, font=(UI_FONT, 11))
        link_entry.pack(pady=5, ipady=3)
        
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

        save_btn = tk.Button(
            button_frame, text="儲存", command=save_new_subtask,
            font=(UI_FONT, 10, "bold"), width=10, relief="flat",
            bg=self.theme["highlight"], fg="#ffffff", cursor="hand2",
            activebackground=self.theme["highlight"], activeforeground="#ffffff",
        )
        save_btn.pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame, text="取消", command=edit_window.destroy,
            font=(UI_FONT, 10), width=10, relief="flat", cursor="hand2",
        ).pack(side=tk.LEFT, padx=5)

        self._apply_dialog_theme(edit_window)
        _center_window(edit_window, self.root)

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
        return _real_text(self.entry).strip()

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
        search_text = _real_text(self.search_entry).lower().strip()
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

        # 更新統計 / 空狀態
        self._update_statistics()
        self._update_empty_state()

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

            # 到期狀態（僅對未完成任務套用）
            due_tag = _due_state(task.due_date, is_effectively_done)
            if due_tag:
                tags.append(due_tag)

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
            search_text = _real_text(self.search_entry).strip()
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
        due_tag = _due_state(task.due_date, is_effectively_done)
        if due_tag:
            tags.append(due_tag)
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
                # dragging 使用主題色系
                dragging_bg = self.theme.get("drop_target", "#cfe8ff") if getattr(self, "theme", None) else "lightblue"
                self.tree.tag_configure("dragging", background=dragging_bg)
            except Exception:
                _logger.debug("套用拖曳樣式失敗", exc_info=True)

        # 已開始拖曳時，標示 hover 目標，提供 drop indicator
        if self.drag_data.get("drag_started"):
            try:
                hover_iid = self.tree.identify_row(event.y)
                prev = self._drop_target_id
                if hover_iid != prev:
                    # 清除舊 drop_target
                    if prev and self.tree.exists(prev):
                        prev_tags = [t for t in (self.tree.item(prev, "tags") or ()) if t != "drop_target"]
                        try:
                            self.tree.item(prev, tags=tuple(prev_tags))
                        except Exception:
                            pass
                    self._drop_target_id = hover_iid or None
                    # 套用新 drop_target（避開自己）
                    if hover_iid and hover_iid != self.drag_data.get("tree_item") and self.tree.exists(hover_iid):
                        cur_tags = list(self.tree.item(hover_iid, "tags") or ())
                        if "drop_target" not in cur_tags:
                            cur_tags.append("drop_target")
                            self.tree.item(hover_iid, tags=tuple(cur_tags))
            except Exception:
                _logger.debug("更新 drop target 失敗", exc_info=True)

    def on_b1_release(self, event):
        # 先清理 drop target hover
        if self._drop_target_id and self.tree.exists(self._drop_target_id):
            try:
                cur = [t for t in (self.tree.item(self._drop_target_id, "tags") or ()) if t != "drop_target"]
                self.tree.item(self._drop_target_id, tags=tuple(cur))
            except Exception:
                pass
        self._drop_target_id = None

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
        search_text = _real_text(self.search_entry).strip()
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
