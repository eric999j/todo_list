import uuid
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any

class Task:
    """代表一個待辦事項的資料結構"""
    def __init__(
        self, 
        text: str, 
        task_id: Optional[str] = None, 
        children: Optional[List['Task']] = None, 
        link: Optional[str] = None, 
        creation_time: Optional[datetime] = None, 
        is_done: bool = False, 
        priority: str = "normal", 
        due_date: Optional[date] = None,
        start_date: Optional[date] = None,
        project: Optional[str] = None
    ) -> None:
        self.id: str = task_id if task_id is not None else str(uuid.uuid4())
        self.text: str = text
        self.children: List['Task'] = children if children is not None else []
        self.link: Optional[str] = link
        self.project: Optional[str] = project
        # use UTC timezone for storage consistency
        if creation_time is not None:
            # ensure it's timezone-aware
            if creation_time.tzinfo is None:
                creation_time = creation_time.astimezone(timezone.utc)
            self.creation_time: datetime = creation_time.astimezone(timezone.utc)
        else:
            self.creation_time: datetime = datetime.now(timezone.utc)
        self.is_done: bool = is_done
        self.priority: str = priority  # "low", "normal", "high"
        self.due_date: Optional[date] = due_date
        self.start_date: Optional[date] = start_date if start_date else self.creation_time.date()

    def to_dict(self) -> Dict[str, Any]:
        """將 Task 物件序列化為字典"""
        def _date_to_iso(value: Any) -> Optional[str]:
            if value is None:
                return None
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return None

        creation_iso: Optional[str] = None
        if self.creation_time:
            creation_iso = (
                self.creation_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )

        return {
            "id": self.id,
            "text": self.text,
            "link": self.link,
            "project": self.project,
            "creation_time": creation_iso,
            "is_done": self.is_done,
            "priority": self.priority,
            "due_date": _date_to_iso(self.due_date),
            "start_date": _date_to_iso(self.start_date),
            "children": [child.to_dict() for child in self.children],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Task':
        """從字典反序列化為 Task 物件"""
        children = [Task.from_dict(child_data) for child_data in data.get("children", [])]
        creation_time_str = data.get("creation_time")
        
        # 解析 creation_time
        if creation_time_str:
            try:
                if creation_time_str.endswith('Z'):
                    creation_time = datetime.fromisoformat(creation_time_str.replace('Z', '+00:00'))
                else:
                    creation_time = datetime.fromisoformat(creation_time_str)
            except (ValueError, TypeError):
                creation_time = datetime.now(timezone.utc)
            
            # ensure UTC-aware
            if creation_time.tzinfo is None:
                creation_time = creation_time.replace(tzinfo=timezone.utc)
            creation_time = creation_time.astimezone(timezone.utc)
        else:
            creation_time = datetime.now(timezone.utc)

        due_date_str = data.get("due_date")
        due_date = None
        if due_date_str:
            try:
                # 優先嘗試以 date (YYYY-MM-DD)
                due_date = date.fromisoformat(due_date_str)
            except (ValueError, TypeError):
                try:
                    # 若包含時間或時區，解析為 datetime 再取 date
                    due_date = datetime.fromisoformat(due_date_str).date()
                except (ValueError, TypeError):
                    due_date = None

        start_date_str = data.get("start_date")
        start_date = None
        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except (ValueError, TypeError):
                try:
                    start_date = datetime.fromisoformat(start_date_str).date()
                except (ValueError, TypeError):
                    start_date = None

        return Task(
            text=data["text"],
            task_id=data["id"],
            children=children,
            link=data.get("link"),
            project=data.get("project"),
            creation_time=creation_time,
            is_done=data.get("is_done", False),
            priority=data.get("priority", "normal"),
            due_date=due_date,
            start_date=start_date
        )
