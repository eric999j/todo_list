from abc import ABC, abstractmethod
from typing import Any, Dict, TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from viewmodel import ViewModel

_logger = get_logger("commands")

class Command(ABC):
    """命令介面的抽象基礎類別
    
    採用逆向操作 (Inverse Operation) 模式實作 Undo/Redo，
    每個子類應實作自己的 undo() 方法來反轉操作，而非備份整個狀態。
    """
    def __init__(self, app: 'ViewModel', **kwargs: Any) -> None:
        self.app: 'ViewModel' = app
        self.params: Dict[str, Any] = kwargs

    @abstractmethod
    def execute(self) -> bool:
        """執行命令的核心邏輯，回傳是否實際執行"""
        pass

    @abstractmethod
    def undo(self) -> None:
        """復原命令的邏輯 - 子類必須實作逆向操作"""
        pass

    def _notify_ui(self, status: str) -> None:
        """通知 UI 更新的輔助方法"""
        if getattr(self.app, 'ui_manager', None):
            try:
                self.app.ui_manager.redraw_tree()
                self.app.ui_manager.set_status(status)
            except Exception:
                _logger.exception("通知 UI 失敗：%s", status)
