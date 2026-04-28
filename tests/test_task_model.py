"""Task 模型序列化/反序列化測試"""
from datetime import date, datetime, timezone

import pytest

from task import Task


def test_to_dict_roundtrip_full_fields():
    src = Task(
        text="買牛奶",
        link="https://example.com",
        priority="high",
        due_date=date(2026, 1, 5),
        start_date=date(2026, 1, 1),
        project="生活",
        is_done=True,
    )
    src.children.append(Task("子任務", priority="low"))

    data = src.to_dict()
    restored = Task.from_dict(data)

    assert restored.id == src.id
    assert restored.text == src.text
    assert restored.link == src.link
    assert restored.priority == src.priority
    assert restored.due_date == src.due_date
    assert restored.start_date == src.start_date
    assert restored.project == src.project
    assert restored.is_done is True
    assert len(restored.children) == 1
    assert restored.children[0].text == "子任務"


def test_creation_time_is_utc_aware():
    t = Task("x")
    assert t.creation_time.tzinfo is not None
    data = t.to_dict()
    assert data["creation_time"].endswith("Z")


def test_from_dict_accepts_legacy_datetime_in_due_date():
    payload = {
        "id": "abc",
        "text": "測試",
        "due_date": "2026-03-04T00:00:00+00:00",
        "start_date": "2026-03-01",
    }
    restored = Task.from_dict(payload)
    assert restored.due_date == date(2026, 3, 4)
    assert restored.start_date == date(2026, 3, 1)


def test_from_dict_handles_missing_optional_fields():
    payload = {"id": "x", "text": "minimal"}
    restored = Task.from_dict(payload)
    assert restored.text == "minimal"
    assert restored.due_date is None
    assert restored.link is None
    assert restored.priority == "normal"
    assert restored.is_done is False


def test_from_dict_invalid_dates_become_none():
    payload = {
        "id": "x",
        "text": "bad",
        "due_date": "not-a-date",
        "start_date": "??",
    }
    restored = Task.from_dict(payload)
    assert restored.due_date is None
    # start_date 解析失敗會 fallback 至 creation_time.date()
    assert restored.start_date == restored.creation_time.date()


def test_to_dict_handles_none_creation_time():
    t = Task("x")
    t.creation_time = None  # type: ignore[assignment]
    data = t.to_dict()
    assert data["creation_time"] is None
