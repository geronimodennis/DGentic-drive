import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from dgentic.settings import get_settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonCollection(Generic[ModelT]):
    def __init__(self, name: str, model_type: type[ModelT], key_field: str = "id") -> None:
        self.name = name
        self.model_type = model_type
        self.key_field = key_field
        self._lock = Lock()

    @property
    def path(self) -> Path:
        data_dir = get_settings().data_dir
        if not data_dir.is_absolute():
            data_dir = get_settings().root_dir / data_dir
        return data_dir / f"{self.name}.json"

    def list(self) -> list[ModelT]:
        with self._lock:
            with self._file_lock():
                return self._load_unlocked()

    def list_quarantined_files(self) -> list[Path]:
        path = self.path
        return sorted(
            item
            for item in path.parent.glob(f"{path.stem}.corrupt-*{path.suffix}")
            if self._is_safe_quarantine(item)
        )

    def restore_quarantine(self, quarantine_path: Path | str | None = None) -> list[ModelT]:
        with self._lock:
            with self._file_lock():
                path = self._resolve_quarantine_path(quarantine_path)
                items = self._read_items_from_path(path)
                if self.path.exists():
                    self._quarantine_unlocked(self.path, reason="pre-restore")
                self._save_unlocked(items)
                return items

    def upsert(self, item: ModelT) -> ModelT:
        with self._lock:
            with self._file_lock():
                items = self._load_unlocked()
                item_id = self._key(item)
                updated = False
                for index, existing in enumerate(items):
                    if self._key(existing) == item_id:
                        items[index] = item
                        updated = True
                        break
                if not updated:
                    items.append(item)
                self._save_unlocked(items)
        return item

    def update(self, item_id: str, updater: Callable[[ModelT], ModelT]) -> ModelT:
        with self._lock:
            with self._file_lock():
                items = self._load_unlocked()
                for index, existing in enumerate(items):
                    if self._key(existing) == item_id:
                        updated = updater(existing)
                        if self._key(updated) != item_id:
                            raise ValueError("Updated item must preserve its collection key.")
                        items[index] = updated
                        self._save_unlocked(items)
                        return updated
        raise KeyError(f"Item not found in collection {self.name}: {item_id}")

    def get(self, item_id: str) -> ModelT | None:
        return next((item for item in self.list() if self._key(item) == item_id), None)

    def _key(self, item: ModelT) -> str:
        return str(getattr(item, self.key_field))

    def _load_unlocked(self) -> list[ModelT]:
        path = self.path
        if path.is_symlink():
            self._quarantine_unlocked(path, reason="corrupt")
            self._save_unlocked([])
            return []
        if not path.exists():
            return []
        try:
            return self._read_items_from_path(path)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
            self._quarantine_unlocked(path, reason="corrupt")
            self._save_unlocked([])
            return []

    def _save_unlocked(self, items: list[ModelT]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            self._quarantine_unlocked(path, reason="corrupt")
        payload = [item.model_dump(mode="json") for item in items]
        temp_path = self._create_temp_save_file(path, json.dumps(payload, indent=2) + "\n")
        if path.is_symlink():
            self._quarantine_unlocked(path, reason="corrupt")
        temp_path.replace(path)

    def _read_items_from_path(self, path: Path) -> list[ModelT]:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_items, list):
            raise ValueError("JSON collection payload must be a list.")
        return [self.model_type.model_validate(raw_item) for raw_item in raw_items]

    def _quarantine_unlocked(self, path: Path, *, reason: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        quarantine_path = path.with_name(f"{path.stem}.{reason}-{timestamp}{path.suffix}")
        counter = 1
        while quarantine_path.exists():
            quarantine_path = path.with_name(
                f"{path.stem}.{reason}-{timestamp}-{counter}{path.suffix}"
            )
            counter += 1
        path.replace(quarantine_path)
        return quarantine_path

    def _create_temp_save_file(self, path: Path, payload: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        counter = 0
        while True:
            suffix = f"{timestamp}-{counter}" if counter else timestamp
            temp_path = path.with_name(f"{path.name}.tmp-{suffix}")
            try:
                with temp_path.open("x", encoding="utf-8") as temp_file:
                    temp_file.write(payload)
                return temp_path
            except FileExistsError:
                counter += 1

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        path = self.path
        lock_path = path.with_name(f"{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _resolve_quarantine_path(self, quarantine_path: Path | str | None) -> Path:
        candidates = self.list_quarantined_files()
        resolved_candidates = {candidate.resolve() for candidate in candidates}
        if quarantine_path is None:
            safe_candidates = [
                candidate for candidate in candidates if self._is_safe_quarantine(candidate)
            ]
            if not safe_candidates:
                raise FileNotFoundError(f"No quarantined files found for collection {self.name}.")
            return safe_candidates[-1]

        path = Path(quarantine_path)
        possible_paths = self._candidate_quarantine_paths(path)
        for candidate in possible_paths:
            resolved = candidate.resolve()
            if self._is_safe_quarantine(resolved) and resolved in resolved_candidates:
                return resolved
        if any(not self._is_safe_quarantine(candidate.resolve()) for candidate in possible_paths):
            raise ValueError("Quarantined file must be in the collection data directory.")
        raise FileNotFoundError(
            f"Quarantined file not found for collection {self.name}: {quarantine_path}"
        )

    def _candidate_quarantine_paths(self, path: Path) -> list[Path]:
        if path.is_absolute():
            return [path]
        settings = get_settings()
        if settings.root_dir.is_absolute():
            root_dir = settings.root_dir
        else:
            root_dir = settings.root_dir.resolve()
        return [self.path.parent / path, root_dir / path, path]

    def _is_safe_quarantine(self, path: Path) -> bool:
        if path.is_symlink():
            return False
        return path.resolve().parent == self.path.parent.resolve()
