# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Strict, bounded JSON input validation using the bundled public schema."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 2 * 1024 * 1024


class InputError(ValueError):
    """The supplied input cannot be reviewed reliably."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("Duplicate JSON object key; remove ambiguity before review.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise InputError("Non-finite JSON numbers are not supported.")


def parse_json(raw: str) -> Any:
    # Bound nesting before invoking the JSON decoder, independently of the
    # interpreter recursion limit. Brackets inside quoted strings do not count.
    nesting, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            nesting += 1
            if nesting > 32:
                raise InputError("JSON nesting exceeds the supported depth of 32.")
        elif char in "]}":
            nesting -= 1
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise InputError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}.") from None
    except (RecursionError, OverflowError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("JSON nesting or numeric representation exceeds supported limits.") from None


def _validate(value: Any, spec: dict, root: dict, path: str = "$", depth: int = 0) -> None:
    # This implements only the schema keywords used by the bundled schema. It does
    # not accept user-supplied schemas or resolve network references.
    if depth > 32:
        raise InputError(f"{path}: nesting exceeds the supported depth.")
    if "$ref" in spec:
        ref = spec["$ref"]
        if not ref.startswith("#/$defs/"):
            raise InputError("Unsupported bundled schema reference.")
        spec = root["$defs"][ref.rsplit("/", 1)[1]]
    if "oneOf" in spec:
        kind = value.get("type") if isinstance(value, dict) else None
        choices = [root["$defs"][s["$ref"].rsplit("/", 1)[1]] for s in spec["oneOf"]]
        selected = [s for s in choices if s["properties"]["type"]["const"] == kind]
        if len(selected) != 1:
            raise InputError(f"{path}.type: expected decision, release, or outcome.")
        _validate(value, selected[0], root, path, depth + 1)
        return
    expected = spec.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
    }
    if expected and not matches.get(expected, False):
        raise InputError(f"{path}: expected {expected}.")
    if "const" in spec and value != spec["const"]:
        raise InputError(f"{path}: unsupported value.")
    if "enum" in spec and value not in spec["enum"]:
        raise InputError(f"{path}: expected one of {', '.join(map(str, spec['enum']))}.")
    if expected == "object":
        required = set(spec.get("required", []))
        missing = required - value.keys()
        if missing:
            raise InputError(f"{path}: missing required field(s): {', '.join(sorted(missing))}.")
        props = spec.get("properties", {})
        if spec.get("additionalProperties") is False and value.keys() - props.keys():
            raise InputError(f"{path}: unexpected field(s); use only the documented, redacted format.")
        for key, child in value.items():
            if key in props:
                _validate(child, props[key], root, f"{path}.{key}", depth + 1)
    elif expected == "array":
        if not spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", 10**9):
            raise InputError(f"{path}: unsupported number of items.")
        for index, child in enumerate(value):
            _validate(child, spec["items"], root, f"{path}[{index}]", depth + 1)
    elif expected == "string":
        if not spec.get("minLength", 0) <= len(value) <= spec.get("maxLength", 10**9):
            raise InputError(f"{path}: unsupported text length.")
        if "pattern" in spec and re.fullmatch(spec["pattern"], value) is None:
            raise InputError(f"{path}: invalid format; use the documented alias or value.")
        if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069 for c in value):
            raise InputError(f"{path}: control or bidirectional formatting characters are not supported.")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise InputError(f"{path}: text must contain valid Unicode characters.") from None
    elif expected == "integer":
        if not spec.get("minimum", -(10**30)) <= value <= spec.get("maximum", 10**30):
            raise InputError(f"{path}: value is outside the supported range.")


def validate_workflow(data: Any) -> dict:
    schema = parse_json(files("payment_control_lab").joinpath("data/workflow.schema.json").read_text("utf-8"))
    _validate(data, schema, schema)
    routes = {r["route_id"] for r in data["routes"]}
    obligations = {o["obligation_id"] for o in data["obligations"]}
    if len(routes) != len(data["routes"]) or len(obligations) != len(data["obligations"]):
        raise InputError("Route and obligation aliases must be unique.")
    event_ids, decision_ids, release_ids = set(), set(), set()
    previous = None
    for event in data["events"]:
        if event["event_id"] in event_ids:
            raise InputError("Event aliases must be unique; deduplicate repeated log records.")
        event_ids.add(event["event_id"])
        try:
            current = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
        except ValueError:
            raise InputError("Event timestamps must be valid ISO 8601 timestamps.") from None
        if current.tzinfo is None or current.utcoffset() is None:
            raise InputError("Every event timestamp must include a timezone.")
        if previous is not None and current < previous:
            raise InputError("Events must be in observed chronological order; the lab never silently sorts them.")
        previous = current
        if event["type"] == "decision":
            if event["decision_id"] in decision_ids:
                raise InputError("Decision aliases must be unique.")
            decision_ids.add(event["decision_id"])
        action = event.get("action")
        if action:
            if action["route_id"] not in routes or action["obligation_id"] not in obligations:
                raise InputError("Every action must reference a declared route and obligation.")
            if event["type"] == "release":
                if action["attempt_id"] in release_ids:
                    raise InputError("Each attempt can have one release record; use distinct aliases for distinct executions.")
                release_ids.add(action["attempt_id"])
    return data


def load_workflow(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise InputError("Cannot read the workflow file; check its path and permissions.") from None
    if len(raw) > MAX_INPUT_BYTES:
        raise InputError("Workflow file exceeds the 2 MiB limit.")
    try:
        data = parse_json(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise InputError("Workflow files must be UTF-8 JSON.") from None
    return validate_workflow(data)


def digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
