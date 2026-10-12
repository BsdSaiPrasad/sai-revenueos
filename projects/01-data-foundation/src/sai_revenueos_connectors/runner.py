"""Orchestrate live vendor reads through the existing P1.2/P1.3 stores."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sai_revenueos_identity import IdentityStore
from sai_revenueos_identity.errors import ConflictError
from sai_revenueos_sources import SourceEvent, SourceStore

from .models import LiveConnector, StreamSyncResult, SyncRunResult, VendorRecord, utc_now


def _subtract_seconds(timestamp: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (parsed - timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


class LiveIngestionRunner:
    """Fetch vendor records and durably process each through P1.3.

    A failed object stream stops at the failed record, so its checkpoint cannot
    cross a gap. Other object streams continue and report their own result.
    Replaying the overlap window is safe because P1.3 event IDs are deterministic.
    """

    def __init__(
        self,
        source_store: SourceStore,
        identity_store: IdentityStore,
        overlap_seconds: int = 300,
    ) -> None:
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds cannot be negative")
        self.source_store = source_store
        self.identity_store = identity_store
        self.overlap_seconds = overlap_seconds

    def _stored_equivalent_event(
        self,
        record: VendorRecord,
        event: SourceEvent,
    ) -> Optional[SourceEvent]:
        """Find a durable envelope for the same stable vendor version."""
        for stored_event in self.source_store.events_for_source_version(
            event.source_system,
            event.source_tenant,
            event.source_object_type,
            event.source_object_id,
            event.event_type,
            event.source_updated_at,
        ):
            if record.same_source_version(stored_event.payload):
                return stored_event
        return None

    def sync(
        self,
        connector: LiveConnector,
        mode: str,
        object_types: Optional[Iterable[str]] = None,
        *,
        until: Optional[str] = None,
        simulate_failure_after: Optional[int] = None,
    ) -> SyncRunResult:
        """Run an initial or incremental sync with per-stream failure isolation."""
        if mode not in {"initial", "incremental"}:
            raise ValueError("mode must be initial or incremental")
        selected = tuple(object_types or connector.supported_object_types)
        unsupported = set(selected) - set(connector.supported_object_types)
        if unsupported:
            raise ValueError("unsupported object types: %s" % ", ".join(sorted(unsupported)))
        run_until = until or utc_now()
        extraction_seed = "%s\x1f%s\x1f%s\x1f%s" % (
            connector.source_system,
            connector.source_tenant,
            mode,
            run_until,
        )
        extraction_id = "p16-extract-%s" % hashlib.sha256(extraction_seed.encode("utf-8")).hexdigest()[:24]
        streams = []
        processed_this_run = 0

        for object_type in selected:
            checkpoint = self.source_store.checkpoint(
                connector.source_system, connector.source_tenant, object_type
            )
            since = None
            if mode == "incremental" and checkpoint is not None:
                since = _subtract_seconds(checkpoint["high_watermark_at"], self.overlap_seconds)
            stream = StreamSyncResult(
                source_system=connector.source_system,
                object_type=object_type,
                mode=mode,
                checkpoint_before=None if checkpoint is None else checkpoint["high_watermark_at"],
            )
            streams.append(stream)
            try:
                for record in connector.fetch_records(object_type, mode, since, run_until):
                    stream.fetched += 1
                    # The source version's update time is the stable observation
                    # boundary for polling replay. The run itself retains a separate
                    # extraction ID in SyncRunResult for operational diagnostics.
                    event = record.to_event(record.source_updated_at)
                    # Salesforce read-side fields can change while the vendor's
                    # actual record version stays fixed. Reuse the first durable
                    # envelope with the same stable content, including envelopes
                    # written before the P1.6 identity fix, so raw history does not
                    # grow merely because RevenueOS polled through its overlap.
                    stored_event = self._stored_equivalent_event(record, event)
                    if stored_event is not None:
                        event = stored_event
                    should_fail = (
                        simulate_failure_after is not None
                        and processed_this_run == simulate_failure_after
                    )
                    try:
                        result = self.source_store.process_event(
                            event,
                            self.identity_store,
                            actor_id="p1.6-live-source-processor",
                            simulate_failure=should_fail,
                        )
                    except ConflictError:
                        # Another worker may have won the first-write race with
                        # the same stable version but different view timestamps.
                        # Retry its immutable envelope; unrelated conflicts remain
                        # visible and still fail the stream.
                        winner = self._stored_equivalent_event(record, event)
                        if winner is None or winner.envelope_sha256 == event.envelope_sha256:
                            raise
                        result = self.source_store.process_event(
                            winner,
                            self.identity_store,
                            actor_id="p1.6-live-source-processor",
                            simulate_failure=should_fail,
                        )
                    processed_this_run += 1
                    stream.processed += int(not result.replayed)
                    stream.replayed += int(result.replayed)
                    stream.tombstones += int(record.event_type == "delete")
                    stream.last_event_id = result.event_id
            except Exception as exc:
                stream.failed += 1
                stream.errors.append("%s: %s" % (type(exc).__name__, str(exc)))
            after = self.source_store.checkpoint(
                connector.source_system, connector.source_tenant, object_type
            )
            stream.checkpoint_after = None if after is None else after["high_watermark_at"]

        return SyncRunResult(
            source_system=connector.source_system,
            source_tenant=connector.source_tenant,
            mode=mode,
            extraction_id=extraction_id,
            streams=streams,
        )
