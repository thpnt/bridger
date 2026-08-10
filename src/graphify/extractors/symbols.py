"""Small private helpers for declaration facts emitted during AST extraction."""

from __future__ import annotations

import re
from pathlib import Path

_SIGNATURE_LIMIT = 500
_BODY_NODE_TYPES = frozenset(
    {
        "body",
        "block",
        "class_body",
        "compound_statement",
        "declaration_list",
        "enum_body",
        "field_declaration_list",
        "function_body",
        "interface_body",
        "struct_body",
    }
)


def make_symbol(
    node,
    source: bytes,
    path: Path,
    *,
    name: str,
    kind: str,
    qualified_name: str | None = None,
    parent_qualified_name: str | None = None,
    language: str | None = None,
    body_node=None,
) -> dict:
    """Create one portable private declaration dictionary from a Tree-sitter node."""
    start_line = node.start_point[0] + 1
    end_row, end_column = node.end_point
    end_line = end_row + (1 if end_column else 0)
    end_line = max(start_line, end_line)
    signature_end = _signature_end(node, body_node)
    signature = _normalize_signature(source[node.start_byte:signature_end])
    return {
        "name": name,
        "qualified_name": qualified_name,
        "kind": kind,
        "source_file": str(path),
        "start_line": start_line,
        "end_line": end_line,
        "parent_qualified_name": parent_qualified_name,
        "signature": signature,
        "language": language,
    }


def make_symbol_from_offsets(
    source: str,
    path: Path,
    *,
    start_offset: int,
    end_offset: int,
    name: str,
    kind: str,
    qualified_name: str | None = None,
    parent_qualified_name: str | None = None,
    language: str | None = None,
    signature_end_offset: int | None = None,
) -> dict:
    """Create one private declaration dictionary from known source offsets."""
    end_offset = max(start_offset + 1, end_offset)
    signature_end = signature_end_offset or end_offset
    return {
        "name": name,
        "qualified_name": qualified_name,
        "kind": kind,
        "source_file": str(path),
        "start_line": source.count("\n", 0, start_offset) + 1,
        "end_line": source.count("\n", 0, end_offset - 1) + 1,
        "parent_qualified_name": parent_qualified_name,
        "signature": _normalize_signature(
            source[start_offset:signature_end].encode("utf-8")
        ),
        "language": language,
    }


def _signature_end(node, body_node) -> int:
    if body_node is not None:
        return body_node.start_byte
    for child in node.children:
        if child.type in _BODY_NODE_TYPES:
            return child.start_byte
    return node.end_byte


def _normalize_signature(raw: bytes) -> str | None:
    text = raw.decode("utf-8", errors="replace")
    normalized = re.sub(r"\s+", " ", text).strip().rstrip("{").strip()
    if not normalized:
        return None
    if len(normalized) > _SIGNATURE_LIMIT:
        normalized = normalized[: _SIGNATURE_LIMIT - 1].rstrip() + "…"
    return normalized
