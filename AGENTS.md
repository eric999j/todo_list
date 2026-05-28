# Project Guidelines

## Architecture

MVVM + Command 模式的 Tkinter 待辦清單應用。

| Layer | File | Responsibility |
|-------|------|----------------|
| Model | `task.py` | `Task` 資料類別，UUID 識別，序列化/反序列化 |
| ViewModel | `viewmodel.py` | 業務邏輯、任務索引（`_task_index`, `_parent_index`）、命令執行 |
| View | `ui_manager.py` | Tkinter UI 渲染與事件處理 |
| Persistence | `task_manager.py` | 檔案讀寫，透過 `UIFallback` Protocol 解耦 UI |
| Commands | `commands/task_commands.py` | 每個命令實作 `execute()` + `undo()`，歷史上限 50 步 |
| Entry | `todo_app.py` | DI 組裝：`TodoApp` → `ViewModel` ↔ `UIManager` |

任務為遞迴樹狀結構（`Task.children`）。父完成 → 子孫遞迴完成；子改為未完成 → 祖先解除完成。

## Build and Test

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # 僅 pytest
python -m pytest -q               # 執行所有測試
python todo_app.py                # 啟動 GUI
```

## Code Style

- Python 3.9+，遵循 PEP 8
- 型別提示：廣泛使用 `typing`（`Optional`, `List`, `Dict`）
- 避免循環匯入：命令模組使用 `TYPE_CHECKING` 守衛
- 命令模組使用相對匯入（`from .base_command import Command`）
- 繁體中文 UI 文字與註解

## Naming

- 類別：PascalCase（`ViewModel`, `AddTaskCommand`）
- 命令類：`<Action><Target>Command`
- 方法：snake_case；私有方法 `_` 前綴
- 布林：`is_` 前綴（`is_done`, `is_dark_mode`）
- 常數：UPPER_SNAKE_CASE（`MAX_HISTORY_SIZE`）

## Testing

- 框架：pytest
- 命名：`test_<功能>_<場景>()`
- ViewModel 直接實例化測試，不需模擬 tkinter
- 命令測試透過 `vm.execute_command()` 驗證 undo/redo
- 樹狀結構測試用 helper 函數建構（如 `build_tree()`）

## Data Format

- `tasks.json`：遞迴 JSON 陣列，`creation_time` 為 UTC ISO 8601（Z 後綴）
- `config.json`：偏好設定（`dark_mode` 等）
- `Task.from_dict()` 容錯解析日期：優先 `date`，fallback `datetime`

## Key Conventions

- 新增操作必須實作為 Command 子類（含 `undo()`）才能支援歷史記錄
- `TaskManager` 透過 Protocol 注入 UI callback，支援 headless 測試
- 相對路徑從模組目錄解析（`os.path.dirname(os.path.abspath(__file__))`)
- JSON 損毀時自動備份為 `.bak`
