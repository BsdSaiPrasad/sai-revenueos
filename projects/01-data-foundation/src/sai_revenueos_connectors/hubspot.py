"""HubSpot scoped-token client and polling connector for P1.6."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote, urlencode

from .http import ApiRequestError, ConfigurationError, JsonHttpClient
from .models import VendorRecord


HUBSPOT_OBJECTS = ("Company", "Contact", "Deal")
OBJECT_PATHS = {"Company": "companies", "Contact": "contacts", "Deal": "deals"}
PROPERTIES = {
    "Company": ("name", "domain", "industry", "country", "hubspot_owner_id", "description"),
    "Contact": ("firstname", "lastname", "email", "associatedcompanyid", "jobtitle"),
    "Deal": ("dealname", "dealstage", "amount", "closedate", "hubspot_owner_id"),
}
TEST_MARKER = "SAI_REVENUEOS_P16_TEST_ONLY"
TEST_NAME = "[SAI TEST] Globex Health"
TEST_DOMAIN = "globex-p16.invalid"


@dataclass
class HubSpotAccessToken:
    """Hold a scoped HubSpot Service Key or existing private-app token."""

    token: str
    tenant: str


def load_hubspot_token(path: Path) -> HubSpotAccessToken:
    """Load a HubSpot token from an ignored mode-600 local file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError("HubSpot credential file is missing or invalid: %s" % path) from exc
    token = document.get("access_token")
    tenant = document.get("tenant")
    if not isinstance(token, str) or not token or not isinstance(tenant, str) or not tenant:
        raise ConfigurationError("HubSpot credential file requires access_token and tenant")
    return HubSpotAccessToken(token=token, tenant=tenant)


class HubSpotConnector:
    """Read HubSpot CRM objects using the supported date-versioned API."""

    source_system = "hubspot"
    supported_object_types = HUBSPOT_OBJECTS

    def __init__(
        self,
        credentials: HubSpotAccessToken,
        http: Optional[JsonHttpClient] = None,
        api_version: str = "2026-09",
        base_url: str = "https://api.hubapi.com",
    ) -> None:
        self.credentials = credentials
        self.http = http or JsonHttpClient()
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")
        self.source_tenant = credentials.tenant

    def _request(
        self,
        method: str,
        url: str,
        *,
        document: Optional[Mapping[str, Any]] = None,
        safe_to_retry: bool = False,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> Any:
        return self.http.request_json(
            method,
            url,
            headers={"Authorization": "Bearer %s" % self.credentials.token},
            document=document,
            safe_to_retry=safe_to_retry,
            expected_statuses=expected_statuses,
        )

    def _object_root(self, object_type: str) -> str:
        try:
            path = OBJECT_PATHS[object_type]
        except KeyError as exc:
            raise ValueError("unsupported HubSpot object: %s" % object_type) from exc
        return "%s/crm/objects/%s/%s" % (self.base_url, self.api_version, path)

    def _list_records(self, object_type: str, archived: bool) -> List[tuple[Dict[str, Any], str]]:
        root = self._object_root(object_type)
        after: Optional[str] = None
        output: List[tuple[Dict[str, Any], str]] = []
        while True:
            params = {
                "limit": "100",
                "archived": "true" if archived else "false",
                "properties": ",".join(PROPERTIES[object_type]),
            }
            if after:
                params["after"] = after
            url = "%s?%s" % (root, urlencode(params))
            page = self._request("GET", url)
            records = page.get("results", [])
            if not isinstance(records, list):
                raise ApiRequestError("GET", url, 200, "HubSpot results must be a list")
            for record in records:
                if not isinstance(record, Mapping):
                    raise ApiRequestError("GET", url, 200, "HubSpot record must be an object")
                output.append((dict(record), url))
            paging = page.get("paging", {})
            next_page = paging.get("next", {}) if isinstance(paging, Mapping) else {}
            next_after = next_page.get("after") if isinstance(next_page, Mapping) else None
            if next_after is None:
                break
            after = str(next_after)
        return output

    @staticmethod
    def _epoch_milliseconds(timestamp: str) -> str:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
        return str(int(parsed.timestamp() * 1000))

    def _search_updated(
        self,
        object_type: str,
        since: str,
        until: str,
    ) -> List[tuple[Dict[str, Any], str]]:
        url = "%s/search" % self._object_root(object_type)
        after: Optional[str] = None
        output: List[tuple[Dict[str, Any], str]] = []
        while True:
            document: Dict[str, Any] = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "hs_lastmodifieddate",
                                "operator": "GTE",
                                "value": self._epoch_milliseconds(since),
                            },
                            {
                                "propertyName": "hs_lastmodifieddate",
                                "operator": "LTE",
                                "value": self._epoch_milliseconds(until),
                            },
                        ]
                    }
                ],
                "properties": list(PROPERTIES[object_type]),
                "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
                "limit": 100,
            }
            if after:
                document["after"] = after
            page = self._request("POST", url, document=document, safe_to_retry=True)
            records = page.get("results", [])
            if not isinstance(records, list):
                raise ApiRequestError("POST", url, 200, "HubSpot search results must be a list")
            for record in records:
                if not isinstance(record, Mapping):
                    raise ApiRequestError("POST", url, 200, "HubSpot record must be an object")
                output.append((dict(record), url))
            paging = page.get("paging", {})
            next_page = paging.get("next", {}) if isinstance(paging, Mapping) else {}
            next_after = next_page.get("after") if isinstance(next_page, Mapping) else None
            if next_after is None:
                break
            after = str(next_after)
        return output

    @staticmethod
    def _within_window(timestamp: str, since: Optional[str], until: str) -> bool:
        if since is not None and timestamp < since:
            return False
        return timestamp <= until

    def fetch_records(
        self,
        object_type: str,
        mode: str,
        since: Optional[str],
        until: str,
    ) -> Iterable[VendorRecord]:
        """Read active changes plus archived records used as deletion tombstones."""
        if object_type not in self.supported_object_types:
            raise ValueError("unsupported HubSpot object: %s" % object_type)
        active = (
            self._list_records(object_type, archived=False)
            if mode == "initial" or since is None
            else self._search_updated(object_type, since, until)
        )
        archived = self._list_records(object_type, archived=True)
        records: List[VendorRecord] = []
        for payload, request_url in active + archived:
            object_id = str(payload.get("id", ""))
            is_archived = payload.get("archived") is True
            updated_at = payload.get("archivedAt") if is_archived else payload.get("updatedAt")
            if not object_id or not isinstance(updated_at, str):
                raise ApiRequestError("GET", request_url, 200, "HubSpot record lacks id or update time")
            if mode == "incremental" and not self._within_window(updated_at, since, until):
                continue
            records.append(
                VendorRecord(
                    self.source_system,
                    self.source_tenant,
                    object_type,
                    object_id,
                    "delete" if is_archived else "upsert",
                    updated_at,
                    payload,
                    "%s|%s" % (updated_at, object_id),
                    "GET" if request_url != "%s/search" % self._object_root(object_type) else "POST",
                    request_url,
                )
            )
        return iter(sorted(records, key=lambda record: (record.source_updated_at, record.object_id, record.event_type)))

    def _search_by_domain(self) -> List[Dict[str, Any]]:
        url = "%s/search" % self._object_root("Company")
        page = self._request(
            "POST",
            url,
            document={
                "filterGroups": [{"filters": [{
                    "propertyName": "domain", "operator": "EQ", "value": TEST_DOMAIN,
                }]}],
                "properties": list(PROPERTIES["Company"]),
                "limit": 100,
            },
            safe_to_retry=True,
        )
        return [dict(item) for item in page.get("results", [])]

    def _get_company(self, object_id: str) -> Dict[str, Any]:
        params = urlencode({"properties": ",".join(PROPERTIES["Company"])})
        url = "%s/%s?%s" % (self._object_root("Company"), quote(object_id), params)
        response = self._request("GET", url)
        if not isinstance(response, Mapping):
            raise ApiRequestError("GET", url, 200, "HubSpot Company must be an object")
        return dict(response)

    def ensure_globex_test_company(self) -> Dict[str, Any]:
        """Create or confirm only the explicitly marked fictional Globex Company."""
        matches = self._search_by_domain()
        if matches:
            safe = [item for item in matches if item.get("properties", {}).get("description") == TEST_MARKER]
            if len(safe) != len(matches) or len(safe) != 1:
                raise ConfigurationError("HubSpot test domain collides with an unmarked or duplicate Company")
            return self._get_company(str(safe[0]["id"]))
        url = self._object_root("Company")
        created = self._request(
            "POST",
            url,
            document={"properties": {
                "name": TEST_NAME,
                "domain": TEST_DOMAIN,
                "country": "United States",
                "description": TEST_MARKER,
            }},
            expected_statuses=(201,),
        )
        object_id = created.get("id")
        if not isinstance(object_id, str):
            raise ApiRequestError("POST", url, 201, "HubSpot create response has no id")
        return self._get_company(object_id)

    def update_globex_test_name(self, object_id: str, new_name: str) -> Dict[str, Any]:
        """Update the test Company only after verifying its ownership marker."""
        current = self._get_company(object_id)
        properties = current.get("properties", {})
        if properties.get("description") != TEST_MARKER or properties.get("domain") != TEST_DOMAIN:
            raise ConfigurationError("refusing to modify an unmarked HubSpot Company")
        url = "%s/%s" % (self._object_root("Company"), quote(object_id))
        self._request(
            "PATCH",
            url,
            document={"properties": {"name": new_name}},
            safe_to_retry=True,
            expected_statuses=(200,),
        )
        return self._get_company(object_id)
