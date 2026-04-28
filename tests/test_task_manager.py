"""TaskManager 載入/儲存/匯出與錯誤路徑測試"""
import json
import os
from typing import Any, List, Optional

import pytest

from task import Task
from task_manager import TaskManager


class RecordingUI:
    def __init__(self, save_path: Optional[str] = None) -> None:
        self.errors: List[tuple] = []
        self.infos: List[tuple] = []
        self.save_path = save_path

    def show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))

    def show_info(self, title: str, message: str) -> None:
        self.infos.append((title, message))

    def ask_save_path(self, **kwargs: Any) -> Optional[str]:
        return self.save_path


def _build_manager(tmp_path, ui: Optional[RecordingUI] = None) -> TaskManager:
    file_path = tmp_path / "tasks.json"
    return TaskManager(data_file=str(file_path), ui=ui or RecordingUI())


def test_load_returns_empty_when_file_missing(tmp_path):
    manager = _build_manager(tmp_path)
    tasks, status = manager.load_tasks()
    assert tasks == []
    assert "新列表" in status


def test_save_then_load_roundtrip(tmp_path):
    manager = _build_manager(tmp_path)
    parent = Task("Parent", priority="high")
    parent.children.append(Task("Child"))

    save_status = manager.save_tasks([parent])
    assert "已儲存" in save_status

    loaded, status = manager.load_tasks()
    assert "完成" in status
    assert len(loaded) == 1
    assert loaded[0].text == "Parent"
    assert loaded[0].priority == "high"
    assert loaded[0].children[0].text == "Child"


def test_load_corrupted_json_creates_backup(tmp_path):
    ui = RecordingUI()
    manager = _build_manager(tmp_path, ui)
    file_path = manager.data_file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{not valid json")

    tasks, status = manager.load_tasks()
    assert tasks == []
    assert "損毀" in status
    assert os.path.exists(file_path + ".bak")
    assert ui.errors  # show_error 被呼叫


def test_export_to_markdown_writes_checklist(tmp_path):
    output = tmp_path / "out.md"
    ui = RecordingUI(save_path=str(output))
    manager = _build_manager(tmp_path, ui)

    parent = Task("Parent", is_done=True)
    parent.children.append(Task("Child"))
    sibling = Task("Linked", link="https://example.com")

    status = manager.export_to_markdown([parent, sibling])
    assert "成功匯出" in status

    content = output.read_text(encoding="utf-8")
    assert "- [x] Parent" in content
    # 子項繼承父項完成狀態
    assert "  - [x] Child" in content
    assert "[Linked](https://example.com)" in content


def test_export_cancelled_when_no_save_path(tmp_path):
    ui = RecordingUI(save_path=None)
    manager = _build_manager(tmp_path, ui)
    status = manager.export_to_markdown([Task("x")])
    assert "取消" in status


def test_export_with_no_tasks_shows_info(tmp_path):
    ui = RecordingUI(save_path=str(tmp_path / "x.md"))
    manager = _build_manager(tmp_path, ui)
    status = manager.export_to_markdown([])
    assert "沒有可匯出" in status
    assert ui.infos
