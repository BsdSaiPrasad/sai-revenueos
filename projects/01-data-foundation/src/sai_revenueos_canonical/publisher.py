"""Publish P1.8-approved identity mappings to Snowflake for P1.9 dbt models."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MAPPING_FIELDS = (
    "external_identity_crosswalk_id",
    "source_record_id",
    "canonical_entity_type",
    "canonical_entity_id",
    "mapping_status",
    "mapping_method",
    "confidence",
    "valid_from",
    "valid_to",
    "reviewed_by",
    "reviewed_at",
)


class PublicationConflictError(RuntimeError):
    """Raised when a publication ID exists with different approved mappings."""


@dataclass(frozen=True)
class IdentityMappingPublicationResult:
    """Summary of one safe identity-mapping publication."""

    publication_id: str
    mapping_count: int
    inserted: bool
    replayed: bool


def _qualified(database: str, schema: str, table: str) -> str:
    for value in (database, schema, table):
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("unsafe Snowflake identifier: %s" % value)
    return "%s.%s.%s" % (database.upper(), schema.upper(), table.upper())


def _mapping_set(document: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if document.get("contract_name") != "identity-resolution-output":
        raise ValueError("unexpected identity-resolution output contract")
    if document.get("contract_version") != "1.0.0":
        raise ValueError("unsupported identity-resolution output version")
    mappings = document.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("identity-resolution mappings must be an array")
    normalized = []
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise ValueError("identity mapping must be an object")
        missing = [name for name in _MAPPING_FIELDS if name not in mapping]
        if missing:
            raise ValueError("identity mapping is missing: %s" % ", ".join(missing))
        if mapping["mapping_status"] != "active":
            raise ValueError("P1.9 accepts only active P1.8 mappings")
        if mapping["canonical_entity_type"] not in {"Account", "Person"}:
            raise ValueError("P1.9 accepts only approved Account or Person mappings")
        normalized.append({name: mapping[name] for name in _MAPPING_FIELDS})
    return sorted(
        normalized,
        key=lambda item: (
            str(item["canonical_entity_type"]),
            str(item["source_record_id"]),
            str(item["external_identity_crosswalk_id"]),
        ),
    )


class IdentityMappingPublisher:
    """Atomically publish a complete active-mapping snapshot for dbt.

    A deterministic publication ID makes an exact retry a no-op. A later
    mapping set creates a new complete snapshot, so revoked mappings disappear
    from current canonical models without deleting earlier publication history.
    """

    def __init__(
        self,
        connection: Any,
        database: str = "SAI_REVENUEOS",
        schema: str = "STAGING",
    ) -> None:
        self.connection = connection
        self.publications = _qualified(database, schema, "P18_IDENTITY_MAPPING_PUBLICATION")
        self.mappings = _qualified(database, schema, "P18_APPROVED_IDENTITY_MAPPING")

    def _ensure_tables(self, cursor: Any) -> None:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS %s (" % self.publications
            + "PUBLICATION_ID VARCHAR NOT NULL, CONTRACT_VERSION VARCHAR NOT NULL, "
            "MAPPING_SET_SHA256 VARCHAR NOT NULL, GENERATED_AT VARCHAR NOT NULL, "
            "MAPPING_COUNT NUMBER NOT NULL, LOADED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP())"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS %s (" % self.mappings
            + "PUBLICATION_ID VARCHAR NOT NULL, EXTERNAL_IDENTITY_CROSSWALK_ID VARCHAR NOT NULL, "
            "SOURCE_RECORD_ID VARCHAR NOT NULL, CANONICAL_ENTITY_TYPE VARCHAR NOT NULL, "
            "CANONICAL_ENTITY_ID VARCHAR NOT NULL, MAPPING_STATUS VARCHAR NOT NULL, "
            "MAPPING_METHOD VARCHAR NOT NULL, CONFIDENCE FLOAT NOT NULL, VALID_FROM VARCHAR NOT NULL, "
            "VALID_TO VARCHAR, REVIEWED_BY VARCHAR NOT NULL, REVIEWED_AT VARCHAR NOT NULL)"
        )

    def publish(self, document: Mapping[str, Any]) -> IdentityMappingPublicationResult:
        """Publish one complete mapping snapshot or safely replay it."""
        mappings = _mapping_set(document)
        payload = {
            "contract_version": document["contract_version"],
            "mappings": mappings,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        publication_id = "p19_pub_%s" % digest[:32]
        cursor = self.connection.cursor()
        try:
            self._ensure_tables(cursor)
            cursor.execute(
                "SELECT MAPPING_SET_SHA256, MAPPING_COUNT FROM %s WHERE PUBLICATION_ID=%%s"
                % self.publications,
                (publication_id,),
            )
            prior = cursor.fetchone()
            if prior is not None:
                if str(prior[0]) != digest or int(prior[1]) != len(mappings):
                    raise PublicationConflictError("publication ID has different mapping content")
                return IdentityMappingPublicationResult(publication_id, len(mappings), False, True)

            cursor.execute(
                "INSERT INTO %s (PUBLICATION_ID, CONTRACT_VERSION, MAPPING_SET_SHA256, "
                "GENERATED_AT, MAPPING_COUNT) VALUES (%%s, %%s, %%s, %%s, %%s)" % self.publications,
                (
                    publication_id,
                    document["contract_version"],
                    digest,
                    document.get("generated_at", ""),
                    len(mappings),
                ),
            )
            if mappings:
                placeholders = ", ".join(["%s"] * (len(_MAPPING_FIELDS) + 1))
                cursor.executemany(
                    "INSERT INTO %s (PUBLICATION_ID, %s) VALUES (%s)"
                    % (
                        self.mappings,
                        ", ".join(name.upper() for name in _MAPPING_FIELDS),
                        placeholders,
                    ),
                    [
                        (publication_id,) + tuple(mapping[name] for name in _MAPPING_FIELDS)
                        for mapping in mappings
                    ],
                )
            self.connection.commit()
            return IdentityMappingPublicationResult(publication_id, len(mappings), True, False)
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()
