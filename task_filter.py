"""任務篩選器模組 - 提供各種任務篩選策略"""
from dataclasses import dataclass
from typing import Any, List
from task import Task


@dataclass(slots=True)
class TaskNode:
    task: Task
    children: List["TaskNode"]

class TaskFilter:
    """任務篩選器基礎類別"""
    
    @staticmethod
    def filter_all(tasks: List[Task]) -> List[Task]:
        """顯示所有任務"""
        return tasks
    
    @staticmethod
    def filter_incomplete(tasks: List[Task]) -> List[TaskNode]:
        """只顯示未完成的任務"""
        result: List[TaskNode] = []
        for task in tasks:
            if not task.is_done:
                filtered_children = TaskFilter.filter_incomplete(task.children)
                result.append(TaskNode(task=task, children=filtered_children))
        return result
    
    @staticmethod
    def filter_high_priority(tasks: List[Task]) -> List[TaskNode]:
        """只顯示高優先級任務"""
        result: List[TaskNode] = []
        for task in tasks:
            filtered_children = TaskFilter.filter_high_priority(task.children)
            if task.priority == "high" or filtered_children:
                result.append(TaskNode(task=task, children=filtered_children))
        return result
    
    @staticmethod
    def filter_completed(tasks: List[Task]) -> List[TaskNode]:
        """只顯示已完成的任務"""
        result: List[TaskNode] = []
        for task in tasks:
            if task.is_done:
                filtered_children = TaskFilter.filter_completed(task.children)
                result.append(TaskNode(task=task, children=filtered_children))
        return result
    
    @staticmethod
    def _wrap_all(tasks: List[Task]) -> List[TaskNode]:
        result: List[TaskNode] = []
        for task in tasks:
            result.append(TaskNode(task=task, children=TaskFilter._wrap_all(task.children)))
        return result

    @staticmethod
    def search_tasks(tasks: List[Any], query: str) -> List[TaskNode]:
        """搜尋包含特定關鍵字的任務"""
        if not query.strip():
            if tasks and isinstance(tasks[0], TaskNode):
                return tasks
            return TaskFilter._wrap_all(tasks)
        
        query_lower = query.lower()
        result: List[TaskNode] = []
        
        for node in tasks:
            if isinstance(node, TaskNode):
                task = node.task
                filtered_children = TaskFilter.search_tasks(node.children, query)
            else:
                task = node
                filtered_children = TaskFilter.search_tasks(task.children, query)

            if query_lower in task.text.lower() or filtered_children:
                result.append(TaskNode(task=task, children=filtered_children))
        
        return result
