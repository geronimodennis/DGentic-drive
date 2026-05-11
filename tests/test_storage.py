import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from dgentic.settings import get_settings
from dgentic.storage import JsonCollection


class StorageRecord(BaseModel):
    id: str
    title: str


@pytest.fixture
def collection(tmp_path, monkeypatch) -> JsonCollection[StorageRecord]:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()

    yield JsonCollection("records", StorageRecord)

    get_settings.cache_clear()


def test_json_collection_quarantines_malformed_json(collection) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")

    items = collection.list()

    quarantined = collection.list_quarantined_files()
    assert items == []
    assert path.read_text(encoding="utf-8") == "[]\n"
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{not valid json"


def test_json_collection_quarantines_invalid_records(collection) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"id": "missing-title"}]), encoding="utf-8")

    items = collection.list()

    quarantined = collection.list_quarantined_files()
    assert items == []
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8")) == [{"id": "missing-title"}]


def test_json_collection_upsert_repairs_active_file_after_quarantine(collection) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    collection.upsert(StorageRecord(id="record-1", title="Recovered"))

    items = collection.list()
    assert [item.id for item in items] == ["record-1"]
    assert collection.list_quarantined_files()


def test_json_collection_restores_valid_quarantine(collection) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    quarantine = path.with_name("records.corrupt-manual.json")
    path.write_text(
        json.dumps([{"id": "current", "title": "Current"}]),
        encoding="utf-8",
    )
    quarantine.write_text(
        json.dumps([{"id": "record-1", "title": "Restored"}]),
        encoding="utf-8",
    )

    restored = collection.restore_quarantine(quarantine.name)

    assert [item.id for item in restored] == ["record-1"]
    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "record-1", "title": "Restored"}]
    pre_restore_files = sorted(path.parent.glob("records.pre-restore-*.json"))
    assert len(pre_restore_files) == 1
    assert json.loads(pre_restore_files[0].read_text(encoding="utf-8")) == [
        {"id": "current", "title": "Current"}
    ]


def test_json_collection_restore_rejects_external_quarantine_path(collection, tmp_path) -> None:
    external = tmp_path / "outside.corrupt.json"
    external.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="collection data directory"):
        collection.restore_quarantine(external)


def test_json_collection_restore_rejects_symlink_quarantine(collection, tmp_path) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    external = tmp_path / "external.json"
    external.write_text(json.dumps([{"id": "external", "title": "Unsafe"}]), encoding="utf-8")
    symlink_path = path.with_name("records.corrupt-zzzz.json")
    try:
        symlink_path.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform.")

    with pytest.raises(FileNotFoundError, match="No quarantined files"):
        collection.restore_quarantine()

    with pytest.raises(ValueError, match="collection data directory"):
        collection.restore_quarantine(symlink_path)


def test_json_collection_does_not_follow_active_symlink_on_list(collection, tmp_path) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    external = tmp_path / "external-active.json"
    external.write_text(
        json.dumps([{"id": "external", "title": "Do not touch"}]),
        encoding="utf-8",
    )
    try:
        path.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform.")

    items = collection.list()

    assert items == []
    assert not path.is_symlink()
    assert path.read_text(encoding="utf-8") == "[]\n"
    assert json.loads(external.read_text(encoding="utf-8")) == [
        {"id": "external", "title": "Do not touch"}
    ]


def test_json_collection_quarantines_broken_active_symlink_on_list(
    collection,
    tmp_path,
) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    missing_target = tmp_path / "missing-active.json"
    try:
        path.symlink_to(missing_target)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform.")

    items = collection.list()

    assert items == []
    assert not path.is_symlink()
    assert path.read_text(encoding="utf-8") == "[]\n"
    assert collection.list_quarantined_files() == []
    assert sorted(path.parent.glob("records.corrupt-*.json"))


def test_json_collection_does_not_follow_active_symlink_on_upsert(collection, tmp_path) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    external = tmp_path / "external-upsert.json"
    external.write_text(
        json.dumps([{"id": "external", "title": "Do not touch"}]),
        encoding="utf-8",
    )
    try:
        path.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform.")

    collection.upsert(StorageRecord(id="record-1", title="Recovered"))

    assert not path.is_symlink()
    assert [item.id for item in collection.list()] == ["record-1"]
    assert json.loads(external.read_text(encoding="utf-8")) == [
        {"id": "external", "title": "Do not touch"}
    ]


def test_json_collection_save_does_not_follow_planted_temp_symlink(
    collection,
    tmp_path,
    monkeypatch,
) -> None:
    path = collection.path
    path.parent.mkdir(parents=True)
    external = tmp_path / "external-temp.json"
    external.write_text("do not touch", encoding="utf-8")
    fixed_now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    planted_temp = path.with_name("records.json.tmp-20260510T120000000000Z")
    try:
        planted_temp.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform.")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("dgentic.storage.datetime", FixedDateTime)

    collection.upsert(StorageRecord(id="record-1", title="Recovered"))

    assert external.read_text(encoding="utf-8") == "do not touch"
    assert planted_temp.is_symlink()
    assert [item.id for item in collection.list()] == ["record-1"]


def test_json_collection_restores_default_relative_quarantine_path(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    get_settings.cache_clear()
    collection = JsonCollection("records", StorageRecord)
    path = collection.path
    path.parent.mkdir(parents=True)
    quarantine = path.with_name("records.corrupt-manual.json")
    quarantine.write_text(
        json.dumps([{"id": "record-1", "title": "Restored"}]),
        encoding="utf-8",
    )

    by_name = collection.restore_quarantine(quarantine.name)
    path.write_text("[]\n", encoding="utf-8")
    by_relative = collection.restore_quarantine(quarantine.relative_to(root_dir))
    path.write_text("[]\n", encoding="utf-8")
    by_absolute = collection.restore_quarantine(quarantine.resolve())

    assert [item.id for item in by_name] == ["record-1"]
    assert [item.id for item in by_relative] == ["record-1"]
    assert [item.id for item in by_absolute] == ["record-1"]
    get_settings.cache_clear()
