"""Read P1.8 inputs from the existing P1.7 dbt staging boundary."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from sai_revenueos_sources import SourceEvent, standardize_event

from .models import StagedIdentityRecord


def _rows(cursor: Any) -> List[Dict[str, Any]]:
    names = [str(column[0]).casefold() for column in cursor.description]
    return [dict(zip(names, values)) for values in cursor.fetchall()]


class SnowflakeStagingReader:
    """Read latest Account and Person rows from P1.7 dbt views.

    The reader receives an already authenticated, read-only Snowflake connection.
    It does not store credentials, build models, or write to Snowflake.
    """

    COMPANY_SQL = """
SELECT
    EVENT_ID, SOURCE_RECORD_ID, SOURCE_SYSTEM, SOURCE_TENANT,
    SOURCE_OBJECT_TYPE, SOURCE_OBJECT_ID, 'Account' AS ENTITY_TYPE,
    NAME, DOMAIN, NULL AS EMAIL, COUNTRY,
    NULL AS EMPLOYER_SOURCE_OBJECT_ID, NULL AS EMPLOYER_NAME,
    NULL AS JOB_TITLE, EVENT_TYPE, IS_DELETED, SOURCE_UPDATED_AT,
    OBSERVED_AT, TRACE_ID, PAYLOAD_SHA256, RAW_PAYLOAD_JSON,
    'STG_CRM_COMPANIES' AS STAGING_MODEL
FROM {database}.{schema}.STG_CRM_COMPANIES
WHERE IS_LATEST_SOURCE_VERSION = TRUE
"""

    PERSON_SQL = """
SELECT
    EVENT_ID, SOURCE_RECORD_ID, SOURCE_SYSTEM, SOURCE_TENANT,
    SOURCE_OBJECT_TYPE, SOURCE_OBJECT_ID, 'Person' AS ENTITY_TYPE,
    NAME, NULL AS DOMAIN, EMAIL, NULL AS COUNTRY,
    EMPLOYER_SOURCE_OBJECT_ID, EMPLOYER_NAME, JOB_TITLE,
    EVENT_TYPE, IS_DELETED, SOURCE_UPDATED_AT, OBSERVED_AT,
    TRACE_ID, PAYLOAD_SHA256, RAW_PAYLOAD_JSON,
    'STG_CRM_PEOPLE' AS STAGING_MODEL
FROM {database}.{schema}.STG_CRM_PEOPLE
WHERE IS_LATEST_SOURCE_VERSION = TRUE
"""

    def __init__(self, connection: Any, database: str = "SAI_REVENUEOS", schema: str = "STAGING") -> None:
        self.connection = connection
        self.database = self._identifier(database)
        self.schema = self._identifier(schema)

    @staticmethod
    def _identifier(value: str) -> str:
        if not value or not value[0].isalpha() or not value.replace("_", "").isalnum():
            raise ValueError("unsafe Snowflake identifier")
        return value.upper()

    def read_records(self, entity_types: Sequence[str] = ("Account", "Person")) -> List[StagedIdentityRecord]:
        """Return latest staged rows, retaining tombstones for explicit handling."""
        unsupported = set(entity_types) - {"Account", "Person"}
        if unsupported:
            raise ValueError("unsupported entity types: %s" % ", ".join(sorted(unsupported)))
        statements = []
        if "Account" in entity_types:
            statements.append(self.COMPANY_SQL)
        if "Person" in entity_types:
            statements.append(self.PERSON_SQL)
        records: List[StagedIdentityRecord] = []
        for template in statements:
            cursor = self.connection.cursor()
            try:
                cursor.execute(template.format(database=self.database, schema=self.schema))
                for row in _rows(cursor):
                    raw = row.get("raw_payload_json")
                    if isinstance(raw, str):
                        try:
                            row["raw_payload_json"] = json.loads(raw)
                        except json.JSONDecodeError:
                            row["raw_payload_json"] = {}
                    records.append(StagedIdentityRecord.from_mapping(row))
            finally:
                cursor.close()
        return sorted(records, key=lambda item: (item.entity_type, item.source_system, item.source_record_id))


class MemoryStagingReader:
    """Use P1.7-shaped rows in credential-free tests and demonstrations."""

    def __init__(self, records: Iterable[StagedIdentityRecord]) -> None:
        self._records = tuple(records)

    def read_records(self, entity_types: Sequence[str] = ("Account", "Person")) -> List[StagedIdentityRecord]:
        allowed = set(entity_types)
        return [record for record in self._records if record.entity_type in allowed]


def record_from_source_event(event: SourceEvent, source_record_id: str) -> StagedIdentityRecord:
    """Adapt one validated P1.3 event to the same shape produced by P1.7 dbt."""
    standard = standardize_event(event)
    key = (event.source_system, event.source_object_type)
    if key in {("salesforce", "Account"), ("hubspot", "Company")}:
        entity_type = "Account"
        name = standard.get("name")
        model = "STG_CRM_COMPANIES"
    elif key in {
        ("salesforce", "Lead"), ("salesforce", "Contact"), ("hubspot", "Contact")
    }:
        entity_type = "Person"
        name = " ".join(
            value for value in (standard.get("first_name"), standard.get("last_name")) if value
        ) or None
        model = "STG_CRM_PEOPLE"
    else:
        raise ValueError("source object is outside the P1.8 Account/Person scope")
    return StagedIdentityRecord(
        event_id=event.event_id,
        source_record_id=source_record_id,
        source_system=event.source_system,
        source_tenant=event.source_tenant,
        source_object_type=event.source_object_type,
        source_object_id=event.source_object_id,
        entity_type=entity_type,
        name=name,
        domain=standard.get("domain"),
        email=standard.get("email"),
        country=standard.get("country") or standard.get("billing_country"),
        employer_source_object_id=standard.get("account_id") or standard.get("company_id"),
        employer_name=standard.get("company"),
        job_title=standard.get("title") or standard.get("job_title"),
        event_type=event.event_type,
        is_deleted=bool(standard.get("is_deleted")),
        source_updated_at=event.source_updated_at,
        observed_at=event.observed_at,
        trace_id=event.trace_id,
        payload_sha256=event.payload_sha256,
        raw_payload=event.payload,
        staging_model=model,
    )
