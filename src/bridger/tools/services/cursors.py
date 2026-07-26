"""Shared opaque cursors for deterministic repository exploration."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping

from bridger.tools.errors import BridgerToolError

CURSOR_SCHEMA_VERSION = 1


class CursorService:
    def __init__(self, source_fingerprint: str) -> None:
        self.source_fingerprint = source_fingerprint

    def filter_hash(self, filters: Mapping[str, object]) -> str:
        encoded = json.dumps(filters, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def encode(
        self,
        tool_name: str,
        filters: Mapping[str, object],
        last_ordering_key: list[object],
    ) -> str:
        payload = {
            "cursor_schema_version": CURSOR_SCHEMA_VERSION,
            "tool_name": tool_name,
            "source_fingerprint": self.source_fingerprint,
            "filter_hash": self.filter_hash(filters),
            "last_ordering_key": last_ordering_key,
        }
        value = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    def decode(
        self, cursor: str, tool_name: str, filters: Mapping[str, object]
    ) -> list[object]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except (
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            binascii.Error,
            TypeError,
        ):
            raise BridgerToolError("invalid_cursor", "Cursor is malformed") from None
        if not isinstance(payload, dict) or payload.get("cursor_schema_version") != (
            CURSOR_SCHEMA_VERSION
        ):
            raise BridgerToolError("invalid_cursor", "Cursor schema is unsupported")
        if payload.get("tool_name") != tool_name:
            raise BridgerToolError("invalid_cursor", "Cursor belongs to another tool")
        if payload.get("source_fingerprint") != self.source_fingerprint:
            raise BridgerToolError("stale_cursor", "Cursor is from another revision")
        if payload.get("filter_hash") != self.filter_hash(filters):
            raise BridgerToolError("invalid_cursor", "Cursor filters do not match")
        key = payload.get("last_ordering_key")
        if not isinstance(key, list):
            raise BridgerToolError("invalid_cursor", "Cursor ordering key is invalid")
        return key
