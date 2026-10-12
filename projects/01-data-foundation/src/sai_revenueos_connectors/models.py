"""Vendor-neutral records and sync results for live P1.6 ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Protocol

from sai_revenueos_sources import SourceEvent


def utc_now() -> str:
    """Return the UTC timestamp format shared with P1.3."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class VendorRecord:
    """One source-native record plus the cursor metadata needed by P1.3."""

    source_system: str
    source_tenant: str
    object_type: str
    object_id: str
    event_type: str
    source_updated_at: str
    payload: Mapping[str, Any]
    cursor: str
    request_method: str
    request_url: str

    def to_event(self, observed_at: str) -> SourceEvent:
        """Wrap the untouched vendor record in the existing P1.3 envelope."""
        payload_json = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest_input = "\x1f".join(
            (
                self.source_system,
                self.source_tenant,
                self.object_type,
                self.object_id,
                self.event_type,
                self.source_updated_at,
                payload_json,
            )
        )
        event_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        # Tracing must be stable for the same vendor version because P1.3 treats
        # the complete envelope as immutable when its deterministic event ID replays.
        stable_extraction_id = "p16-version-%s" % event_digest[:24]
        return SourceEvent.from_dict(
            {
                "contract_version": "1.0.0",
                "event_id": "p16-%s" % event_digest,
                "source": {
                    "system": self.source_system,
                    "tenant": self.source_tenant,
                    "object_type": self.object_type,
                    "object_id": self.object_id,
                },
                "event_type": self.event_type,
                "timestamps": {
                    "source_updated_at": self.source_updated_at,
                    "observed_at": observed_at,
                },
                "tracing": {
                    "trace_id": "trace-%s" % event_digest[:24],
                    "extraction_id": stable_extraction_id,
                },
                "checkpoint": {
                    "stream_name": self.object_type,
                    "cursor": self.cursor,
                    "high_watermark_at": self.source_updated_at,
                },
                "payload": dict(self.payload),
            }
        )


class LiveConnector(Protocol):
    """Interface shared by Salesforce and HubSpot connector implementations."""

    source_system: str
    source_tenant: str
    supported_object_types: tuple[str, ...]

    def fetch_records(
        self,
        object_type: str,
        mode: str,
        since: Optional[str],
        until: str,
    ) -> Iterable[VendorRecord]:
        """Yield source records in nondecreasing source-update order."""


@dataclass
class StreamSyncResult:
    """Summarize one object stream without exposing payload or credentials."""

    source_system: str
    object_type: str
    mode: str
    fetched: int = 0
    processed: int = 0
    replayed: int = 0
    tombstones: int = 0
    failed: int = 0
    last_event_id: Optional[str] = None
    checkpoint_before: Optional[str] = None
    checkpoint_after: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class SyncRunResult:
    """Combine independently isolated stream results for one connector run."""

    source_system: str
    source_tenant: str
    mode: str
    extraction_id: str
    streams: List[StreamSyncResult]

    @property
    def succeeded(self) -> bool:
        return all(stream.failed == 0 for stream in self.streams)

    @property
    def processed(self) -> int:
        return sum(stream.processed for stream in self.streams)

    @property
    def replayed(self) -> int:
        return sum(stream.replayed for stream in self.streams)
