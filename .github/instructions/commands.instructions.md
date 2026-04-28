---
description: "Use when creating, modifying, or reviewing command classes in the commands/ module. Covers Command pattern conventions, undo/redo requirements, and naming rules."
applyTo: "commands/**/*.py"
---

# Command 模式規範

## 結構要求

每個命令必須繼承 `Command` 基類並實作：
- `execute()` — 執行操作
- `undo()` — **逆向操作**還原狀態（非快照式）

```python
from .base_command import Command

class <Action><Target>Command(Command):
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        # 在此宣告 undo 所需的備份欄位

    def execute(self) -> None:
        # 1. 從 self.params 取得參數
        # 2. 備份 undo 需要的舊值
        # 3. 執行操作

    def undo(self) -> None:
        # 反轉 execute 的效果
        # 結尾呼叫 self._notify_ui("已復原：…")
```

## 命名

- 類別：`<Action><Target>Command`（如 `AddTaskCommand`、`ToggleDoneStatusCommand`）
- 備份欄位：`_` 前綴（如 `_old_values`、`_added_task_id`）

## Undo 實作原則

- 採用逆向操作模式，不備份整個狀態快照
- `execute()` 中必須備份 undo 所需的最小資訊
- 涉及樹狀結構變動時，undo 結尾呼叫 `self.app.rebuild_task_index()`
- 使用 `copy.deepcopy()` 備份 Task 物件（含 children）

## 匯入規則

- 模組內使用相對匯入：`from .base_command import Command`
- 避免循環匯入：使用 `TYPE_CHECKING` 守衛引用 `ViewModel`
- 參數型別使用 `Any` 以避免對 ViewModel 的直接依賴

## UI 通知

- 命令不應直接操作 UI 元件（對話框、輸入框等）
- 透過 `self._notify_ui(status_message)` 更新狀態列
- 狀態訊息使用繁體中文（如 `"已復原：移除新增的任務"`）

## 註冊流程

新命令建立後須從 ViewModel 透過 `execute_command(cmd)` 呼叫，確保自動記錄至 `CommandHistory`。
