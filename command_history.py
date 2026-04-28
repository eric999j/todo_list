from typing import List, Optional
from commands.base_command import Command

class CommandHistory:
    """管理命令歷史以支援 Undo/Redo 功能
    
    設有最大堆疊限制以避免記憶體無限膨脹。
    """
    MAX_HISTORY_SIZE = 50  # 最多保留 50 步歷史
    
    def __init__(self) -> None:
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

    def record(self, command: Command) -> None:
        """記錄已執行的命令"""
        self.undo_stack.append(command)
        self.redo_stack.clear()  # 當執行新命令時清空 redo 堆疊
        
        # 限制堆疊大小
        if len(self.undo_stack) > self.MAX_HISTORY_SIZE:
            self.undo_stack.pop(0)  # 移除最舊的命令

    def undo(self) -> Optional[Command]:
        """復原最後一個命令"""
        if not self.undo_stack:
            return None
        
        command = self.undo_stack.pop()
        self.redo_stack.append(command)
        return command

    def redo(self) -> Optional[Command]:
        """重做最後復原的命令"""
        if not self.redo_stack:
            return None
        
        command = self.redo_stack.pop()
        self.undo_stack.append(command)
        return command

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def clear(self) -> None:
        """清空歷史"""
        self.undo_stack.clear()
        self.redo_stack.clear()
