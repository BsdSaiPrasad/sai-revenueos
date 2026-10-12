"""Load P1.3 source contracts and validate vendor-neutral event envelopes.

Salesforce and HubSpot payloads remain source-native JSON. RevenueOS validates a
small essential field set for immediate use while retaining every supplied field
in raw history. This module has no live vendor client and makes no network calls.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from sai_revenueos_identity.errors import ValidationError


CONTRACT_VERSION = "1.0.0"
SUPPORTED_SYSTEMS = frozenset({"salesforce", "hubspot"})
EVENT_TYPES = frozenset({"upsert", "delete"})
CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts"
_MISSING = object()
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_TEXT_LENGTH = 512


def _require_mapping(name: str, value: Any) -> Mapping[str, Any]:
    """Return a mapping or reject malformed envelope structure."""
    if not isinstance(value, Mapping):
        raise ValidationError("%s must be an object" % name)
    return value


def _require_text(name: str, value: Any) -> str:
    """Return trimmed non-empty text suitable for an event identifier."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be a non-empty string" % name)
    trimmed = value.strip()
    if len(trimmed) > _MAX_TEXT_LENGTH:
        raise ValidationError("%s exceeds %d characters" % (name, _MAX_TEXT_LENGTH))
    if _CONTROL_CHARACTERS.search(trimmed):
        raise ValidationError("%s cannot contain control characters" % name)
    return trimmed


def _require_exact_keys(name: str, value: Mapping[str, Any], expected: set[str]) -> None:
    """Enforce the versioned envelope rather than silently accepting misspellings."""
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise ValidationError("%s is missing: %s" % (name, ", ".join(sorted(missing))))
    if extra:
        raise ValidationError("%s has unsupported fields: %s" % (name, ", ".join(sorted(extra))))


def normalize_timestamp(name: str, value: Any) -> str:
    """Validate an ISO 8601 timestamp and return a comparable UTC value."""
    text = _require_text(name, value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("%s must be an ISO 8601 timestamp" % name) from exc
    if parsed.tzinfo is None:
        raise ValidationError("%s must include a timezone" % name)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceEvent:
    """One validated source-event envelope with its complete vendor payload.

    The envelope supplies stable replay identity, source namespace, event timing,
    tracing, and checkpoint metadata. ``raw_payload_json`` contains all payload
    fields before RevenueOS selects its small standardized subset.
    """

    contract_version: str
    event_id: str
    source_system: str
    source_tenant: str
    source_object_type: str
    source_object_id: str
    event_type: str
    source_updated_at: str
    observed_at: str
    trace_id: str
    extraction_id: str
    stream_name: str
    checkpoint_cursor: str
    checkpoint_high_watermark_at: str
    raw_payload_json: str
    payload_sha256: str
    envelope_sha256: str

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "SourceEvent":
        """Validate a version 1 envelope without standardizing its payload."""
        root = _require_mapping("event", document)
        _require_exact_keys(
            "event",
            root,
            {"contract_version", "event_id", "source", "event_type", "timestamps", "tracing", "checkpoint", "payload"},
        )
        if root["contract_version"] != CONTRACT_VERSION:
            raise ValidationError("unsupported source-event contract version")

        source = _require_mapping("source", root["source"])
        timestamps = _require_mapping("timestamps", root["timestamps"])
        tracing = _require_mapping("tracing", root["tracing"])
        checkpoint = _require_mapping("checkpoint", root["checkpoint"])
        payload = _require_mapping("payload", root["payload"])
        _require_exact_keys("source", source, {"system", "tenant", "object_type", "object_id"})
        _require_exact_keys("timestamps", timestamps, {"source_updated_at", "observed_at"})
        _require_exact_keys("tracing", tracing, {"trace_id", "extraction_id"})
        _require_exact_keys("checkpoint", checkpoint, {"stream_name", "cursor", "high_watermark_at"})

        supplied_system = _require_text("source.system", source["system"])
        system = supplied_system.casefold()
        if system not in SUPPORTED_SYSTEMS:
            raise ValidationError("unsupported source system: %s" % system)
        if supplied_system != system:
            raise ValidationError("source.system must use the contract's lowercase code")
        supplied_event_type = _require_text("event_type", root["event_type"])
        event_type = supplied_event_type.casefold()
        if event_type not in EVENT_TYPES:
            raise ValidationError("event_type must be upsert or delete")
        if supplied_event_type != event_type:
            raise ValidationError("event_type must use the contract's lowercase code")

        raw_payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        payload_sha256 = hashlib.sha256(raw_payload_json.encode("utf-8")).hexdigest()
        immutable_envelope = {
            "contract_version": CONTRACT_VERSION,
            "event_id": _require_text("event_id", root["event_id"]),
            "source": dict(source),
            "event_type": event_type,
            "timestamps": dict(timestamps),
            "tracing": dict(tracing),
            "checkpoint": dict(checkpoint),
            "payload": json.loads(raw_payload_json),
        }
        envelope_sha256 = hashlib.sha256(
            json.dumps(immutable_envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        return cls(
            contract_version=CONTRACT_VERSION,
            event_id=immutable_envelope["event_id"],
            source_system=system,
            source_tenant=_require_text("source.tenant", source["tenant"]),
            source_object_type=_require_text("source.object_type", source["object_type"]),
            source_object_id=_require_text("source.object_id", source["object_id"]),
            event_type=event_type,
            source_updated_at=normalize_timestamp("timestamps.source_updated_at", timestamps["source_updated_at"]),
            observed_at=normalize_timestamp("timestamps.observed_at", timestamps["observed_at"]),
            trace_id=_require_text("tracing.trace_id", tracing["trace_id"]),
            extraction_id=_require_text("tracing.extraction_id", tracing["extraction_id"]),
            stream_name=_require_text("checkpoint.stream_name", checkpoint["stream_name"]),
            checkpoint_cursor=_require_text("checkpoint.cursor", checkpoint["cursor"]),
            checkpoint_high_watermark_at=normalize_timestamp(
                "checkpoint.high_watermark_at", checkpoint["high_watermark_at"]
            ),
            raw_payload_json=raw_payload_json,
            payload_sha256=payload_sha256,
            envelope_sha256=envelope_sha256,
        )

    @property
    def payload(self) -> Dict[str, Any]:
        """Return a fresh copy of the complete source-native payload."""
        return json.loads(self.raw_payload_json)


class SourceContractRegistry:
    """Load the checked-in Salesforce and HubSpot version 1 contracts."""

    def __init__(self, contract_dir: Path = CONTRACT_DIR) -> None:
        self._contracts: Dict[str, Dict[str, Any]] = {}
        for system in sorted(SUPPORTED_SYSTEMS):
            path = contract_dir / ("%s-source.v1.json" % system)
            try:
                contract = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationError("cannot load %s source contract" % system) from exc
            if contract.get("contract_version") != CONTRACT_VERSION:
                raise ValidationError("%s source contract has an unsupported version" % system)
            if contract.get("source_system") != system or not isinstance(contract.get("objects"), dict):
                raise ValidationError("%s source contract is malformed" % system)
            self._contracts[system] = contract

    def contract(self, source_system: str) -> Dict[str, Any]:
        """Return one loaded source contract."""
        system = _require_text("source_system", source_system).casefold()
        try:
            return self._contracts[system]
        except KeyError as exc:
            raise ValidationError("unsupported source system: %s" % system) from exc

    def object_spec(self, source_system: str, source_object_type: str) -> Dict[str, Any]:
        """Return the essential-object mapping for one source object type."""
        contract = self.contract(source_system)
        try:
            return contract["objects"][source_object_type]
        except KeyError as exc:
            raise ValidationError(
                "%s object type is not in the version 1 essential model: %s"
                % (source_system, source_object_type)
            ) from exc


def _path_value(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    """Read a nested vendor field, returning a sentinel when it is absent."""
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _validate_field(path: Sequence[str], value: Any, field_type: str) -> None:
    """Validate one contracted essential field while allowing unknown raw fields."""
    label = ".".join(path)
    if field_type == "string":
        valid = isinstance(value, str) and bool(value.strip())
    elif field_type == "nullable_string":
        valid = value is None or isinstance(value, str)
    elif field_type == "boolean":
        valid = isinstance(value, bool)
    elif field_type == "nullable_number":
        valid = value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
    else:
        raise ValidationError("source contract uses unsupported field type: %s" % field_type)
    if not valid:
        raise ValidationError("payload field %s must be %s" % (label, field_type))


def standardize_event(
    event: SourceEvent,
    registry: Optional[SourceContractRegistry] = None,
) -> Dict[str, Any]:
    """Validate essential fields and return the contracted standardized subset.

    Raw payload persistence is the caller's responsibility and must happen before
    this function runs. Unknown vendor fields are intentionally ignored here but
    remain present in ``SourceEvent.raw_payload_json``.
    """
    contracts = registry or SourceContractRegistry()
    spec = contracts.object_spec(event.source_system, event.source_object_type)
    payload = event.payload

    payload_id = _path_value(payload, spec["id_path"])
    if payload_id is _MISSING or str(payload_id) != event.source_object_id:
        raise ValidationError("payload object ID does not match the event envelope")

    deletion_value = _path_value(payload, spec["deletion_path"])
    if event.event_type == "delete":
        if deletion_value is not True:
            raise ValidationError("delete event must contain the vendor deletion marker")
    elif deletion_value is True:
        raise ValidationError("upsert event cannot contain an active deletion marker")

    if event.event_type == "upsert":
        for path in spec["required_upsert_paths"]:
            if _path_value(payload, path) is _MISSING:
                raise ValidationError("payload is missing required field: %s" % ".".join(path))

    timestamp_path = spec["updated_at_path"]
    if event.event_type == "delete" and "deleted_at_path" in spec:
        deleted_at = _path_value(payload, spec["deleted_at_path"])
        if deleted_at is not _MISSING:
            timestamp_path = spec["deleted_at_path"]
    payload_updated_at = _path_value(payload, timestamp_path)
    if payload_updated_at is not _MISSING:
        if normalize_timestamp("payload source update time", payload_updated_at) != event.source_updated_at:
            raise ValidationError("payload update time does not match the event envelope")

    standardized: Dict[str, Any] = {}
    for output_name, field in spec["fields"].items():
        value = _path_value(payload, field["path"])
        if value is _MISSING:
            continue
        _validate_field(field["path"], value, field["type"])
        standardized[output_name] = value
    standardized["source_object_id"] = event.source_object_id
    standardized["source_updated_at"] = event.source_updated_at
    standardized["is_deleted"] = event.event_type == "delete"
    return standardized
