from __future__ import annotations

"""Object storage abstraction placeholder.

This module will encapsulate upload, download, and signed-URL generation for
structure files and batch exports.
"""


class ObjectStore:
    def put_bytes(self, key: str, payload: bytes) -> None:
        _ = (key, payload)

    def signed_download_url(self, key: str) -> str:
        return f"https://downloads.abby.local/{key}"
