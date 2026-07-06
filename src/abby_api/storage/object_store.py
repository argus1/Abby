from __future__ import annotations

from json import dumps
from pathlib import Path

from abby_api.core.config import get_settings

"""Local object-store abstraction for dev/testing.

This implementation writes artifacts to a local directory while preserving
key-based semantics compatible with cloud object stores.
"""

DEFAULT_OBJECT_STORE_DIR = Path(__file__).resolve().parents[3] / "data" / "object_store"


def _sanitize_key(key: str) -> str:
    cleaned = key.strip().lstrip("/")
    if not cleaned or ".." in cleaned:
        raise ValueError("Invalid object-store key.")
    return cleaned


class ObjectStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_OBJECT_STORE_DIR

    def put_bytes(self, key: str, payload: bytes) -> None:
        safe_key = _sanitize_key(key)
        destination = self.base_dir / safe_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def put_json(self, key: str, payload: dict[str, object]) -> None:
        data = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.put_bytes(key, data)

    def exists(self, key: str) -> bool:
        safe_key = _sanitize_key(key)
        return (self.base_dir / safe_key).exists()

    def get_bytes(self, key: str) -> bytes | None:
        safe_key = _sanitize_key(key)
        path = self.base_dir / safe_key
        if not path.exists():
            return None
        return path.read_bytes()

    def signed_download_url(self, key: str) -> str:
        safe_key = _sanitize_key(key)
        settings = get_settings()
        endpoint = settings.object_storage_endpoint.rstrip("/")
        bucket = settings.object_storage_bucket.strip().strip("/")
        return f"{endpoint}/{bucket}/{safe_key}"
