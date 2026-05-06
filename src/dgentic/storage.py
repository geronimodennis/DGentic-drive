import json
from pathlib import Path
from threading import Lock
from typing import Generic, TypeVar

from pydantic import BaseModel

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
            return self._load_unlocked()

    def upsert(self, item: ModelT) -> ModelT:
        with self._lock:
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

    def get(self, item_id: str) -> ModelT | None:
        return next((item for item in self.list() if self._key(item) == item_id), None)

    def _key(self, item: ModelT) -> str:
        return str(getattr(item, self.key_field))

    def _load_unlocked(self) -> list[ModelT]:
        path = self.path
        if not path.exists():
            return []
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        return [self.model_type.model_validate(raw_item) for raw_item in raw_items]

    def _save_unlocked(self, items: list[ModelT]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in items]
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
