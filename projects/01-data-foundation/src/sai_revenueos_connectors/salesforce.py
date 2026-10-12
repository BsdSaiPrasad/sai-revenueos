"""Salesforce OAuth 2.0 client and polling connector for P1.6."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol
from urllib.parse import quote, urlencode

from .http import ApiRequestError, ConfigurationError, JsonHttpClient
from .models import VendorRecord


SALESFORCE_OBJECTS = ("Account", "Lead", "Contact", "Opportunity")
TEST_MARKER = "SAI_REVENUEOS_P16_TEST_ONLY"
TEST_NAME = "[SAI TEST] Globex Health"
TEST_WEBSITE = "https://globex-p16.invalid"
READ_SIDE_FIELDS = ("attributes", "LastViewedDate", "LastReferencedDate")


class SalesforceTokenProvider(Protocol):
    """Supply and refresh an OAuth access token without exposing it to logs."""

    @property
    def instance_url(self) -> str:
        """Return the Salesforce instance URL issued by OAuth."""

    @property
    def tenant(self) -> str:
        """Return a stable org identifier used in P1.2 source identity."""

    def access_token(self, force_refresh: bool = False) -> str:
        """Return an access token, refreshing it when requested."""


@dataclass
class StaticSalesforceToken:
    """Inject a token in tests or short-lived local sessions."""

    token: str
    instance_url: str
    tenant: str

    def access_token(self, force_refresh: bool = False) -> str:
        return self.token


class SalesforceOAuthFile:
    """Refresh Salesforce OAuth credentials stored in an ignored mode-600 file."""

    def __init__(self, path: Path, http: Optional[JsonHttpClient] = None) -> None:
        self.path = path
        self.http = http or JsonHttpClient()
        try:
            self._credentials = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError("Salesforce OAuth file is missing or invalid: %s" % path) from exc
        required = {"client_id", "refresh_token", "instance_url", "tenant", "login_url"}
        missing = required - set(self._credentials)
        if missing:
            raise ConfigurationError("Salesforce OAuth file is missing fields: %s" % ", ".join(sorted(missing)))
        self._access_token = self._credentials.get("access_token")

    @property
    def instance_url(self) -> str:
        return str(self._credentials["instance_url"]).rstrip("/")

    @property
    def tenant(self) -> str:
        return str(self._credentials["tenant"])

    def access_token(self, force_refresh: bool = False) -> str:
        if self._access_token and not force_refresh:
            return str(self._access_token)
        form = {
            "grant_type": "refresh_token",
            "client_id": str(self._credentials["client_id"]),
            "refresh_token": str(self._credentials["refresh_token"]),
        }
        client_secret = self._credentials.get("client_secret")
        if client_secret:
            form["client_secret"] = str(client_secret)
        response = self.http.request_json(
            "POST",
            "%s/services/oauth2/token" % str(self._credentials["login_url"]).rstrip("/"),
            form=form,
            safe_to_retry=True,
        )
        token = response.get("access_token") if isinstance(response, Mapping) else None
        if not isinstance(token, str) or not token:
            raise ConfigurationError("Salesforce refresh response did not contain an access token")
        self._access_token = token
        if isinstance(response.get("instance_url"), str):
            self._credentials["instance_url"] = response["instance_url"]
        # Rotation-aware providers may return a replacement refresh token.
        if isinstance(response.get("refresh_token"), str):
            self._credentials["refresh_token"] = response["refresh_token"]
        self._credentials["access_token"] = token
        self.path.write_text(json.dumps(self._credentials, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(self.path, 0o600)
        return token


class SalesforceConnector:
    """Read Salesforce records through REST query and replication resources."""

    source_system = "salesforce"
    supported_object_types = SALESFORCE_OBJECTS

    def __init__(
        self,
        token_provider: SalesforceTokenProvider,
        http: Optional[JsonHttpClient] = None,
        api_version: str = "latest",
    ) -> None:
        self.token_provider = token_provider
        self.http = http or JsonHttpClient()
        self.api_version = api_version
        self.source_tenant = token_provider.tenant

    @property
    def api_root(self) -> str:
        return "%s/services/data/%s" % (self.token_provider.instance_url.rstrip("/"), self.api_version)

    def _request(
        self,
        method: str,
        url: str,
        *,
        document: Optional[Mapping[str, Any]] = None,
        safe_to_retry: bool = False,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> Any:
        headers = {"Authorization": "Bearer %s" % self.token_provider.access_token()}
        try:
            return self.http.request_json(
                method,
                url,
                headers=headers,
                document=document,
                safe_to_retry=safe_to_retry,
                expected_statuses=expected_statuses,
            )
        except ApiRequestError as exc:
            if exc.status != 401:
                raise
        # One forced OAuth refresh handles an expired access token; retry policy
        # remains bounded inside JsonHttpClient.
        headers["Authorization"] = "Bearer %s" % self.token_provider.access_token(force_refresh=True)
        return self.http.request_json(
            method,
            url,
            headers=headers,
            document=document,
            safe_to_retry=safe_to_retry,
            expected_statuses=expected_statuses,
        )

    @staticmethod
    def _salesforce_time(value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _event_identity_fields() -> tuple[str, ...]:
        """Exclude metadata changed by a read while preserving it in raw JSON."""
        return READ_SIDE_FIELDS

    def _query_all(self, soql: str) -> Iterable[tuple[Dict[str, Any], str]]:
        url = "%s/queryAll/?%s" % (self.api_root, urlencode({"q": soql}))
        while url:
            page_url = url
            page = self._request("GET", page_url)
            records = page.get("records", [])
            if not isinstance(records, list):
                raise ApiRequestError("GET", page_url, 200, "Salesforce records must be a list")
            for record in records:
                if not isinstance(record, Mapping):
                    raise ApiRequestError("GET", page_url, 200, "Salesforce record must be an object")
                yield dict(record), page_url
            next_path = page.get("nextRecordsUrl")
            url = "%s%s" % (self.token_provider.instance_url.rstrip("/"), next_path) if next_path else ""

    def _get_record(self, object_type: str, object_id: str) -> tuple[Dict[str, Any], str]:
        url = "%s/sobjects/%s/%s" % (self.api_root, quote(object_type), quote(object_id))
        response = self._request("GET", url)
        if not isinstance(response, Mapping):
            raise ApiRequestError("GET", url, 200, "Salesforce record must be an object")
        return dict(response), url

    def _initial_records(self, object_type: str) -> List[VendorRecord]:
        soql = "SELECT Id, LastModifiedDate, IsDeleted FROM %s ORDER BY LastModifiedDate, Id" % object_type
        records: List[VendorRecord] = []
        for summary, request_url in self._query_all(soql):
            object_id = str(summary.get("Id", ""))
            if not object_id:
                raise ApiRequestError("GET", request_url, 200, "Salesforce record has no Id")
            is_deleted = summary.get("IsDeleted") is True
            payload = summary
            if not is_deleted:
                payload, request_url = self._get_record(object_type, object_id)
            updated_at = payload.get("LastModifiedDate") or summary.get("LastModifiedDate")
            if not isinstance(updated_at, str):
                raise ApiRequestError("GET", request_url, 200, "Salesforce record has no LastModifiedDate")
            records.append(
                VendorRecord(
                    self.source_system,
                    self.source_tenant,
                    object_type,
                    object_id,
                    "delete" if is_deleted else "upsert",
                    updated_at,
                    payload,
                    "%s|%s" % (updated_at, object_id),
                    "GET",
                    request_url,
                    self._event_identity_fields(),
                )
            )
        return records

    def _incremental_records(self, object_type: str, since: str, until: str) -> List[VendorRecord]:
        start = self._salesforce_time(since)
        end = self._salesforce_time(until)
        records: List[VendorRecord] = []
        updated_url = "%s/sobjects/%s/updated/?%s" % (
            self.api_root,
            quote(object_type),
            urlencode({"start": start, "end": end}),
        )
        updated = self._request("GET", updated_url)
        for object_id in updated.get("ids", []):
            payload, request_url = self._get_record(object_type, str(object_id))
            updated_at = payload.get("LastModifiedDate")
            if not isinstance(updated_at, str):
                raise ApiRequestError("GET", request_url, 200, "Salesforce record has no LastModifiedDate")
            records.append(
                VendorRecord(
                    self.source_system,
                    self.source_tenant,
                    object_type,
                    str(object_id),
                    "upsert",
                    updated_at,
                    payload,
                    "%s|%s" % (updated_at, object_id),
                    "GET",
                    request_url,
                    self._event_identity_fields(),
                )
            )

        deleted_url = "%s/sobjects/%s/deleted/?%s" % (
            self.api_root,
            quote(object_type),
            urlencode({"start": start, "end": end}),
        )
        deleted = self._request("GET", deleted_url)
        for item in deleted.get("deletedRecords", []):
            object_id = str(item.get("id", ""))
            deleted_at = item.get("deletedDate")
            if not object_id or not isinstance(deleted_at, str):
                raise ApiRequestError("GET", deleted_url, 200, "Salesforce deletion is malformed")
            payload = {
                "Id": object_id,
                "IsDeleted": True,
                "DeletedDate": deleted_at,
                # Get Deleted uses lower-camel-case fields that do not match the
                # sObject contract. Keep that endpoint item intact alongside the
                # contract fields so the original vendor evidence is never lost.
                "SalesforceDeletedRecord": dict(item),
            }
            records.append(
                VendorRecord(
                    self.source_system,
                    self.source_tenant,
                    object_type,
                    object_id,
                    "delete",
                    deleted_at,
                    payload,
                    "%s|%s" % (deleted_at, object_id),
                    "GET",
                    deleted_url,
                    self._event_identity_fields(),
                )
            )
        return records

    def fetch_records(
        self,
        object_type: str,
        mode: str,
        since: Optional[str],
        until: str,
    ) -> Iterable[VendorRecord]:
        """Read a full snapshot or Salesforce replication window."""
        if object_type not in self.supported_object_types:
            raise ValueError("unsupported Salesforce object: %s" % object_type)
        if mode == "initial":
            records = self._initial_records(object_type)
        elif mode == "incremental" and since is not None:
            records = self._incremental_records(object_type, since, until)
        elif mode == "incremental":
            records = self._initial_records(object_type)
        else:
            raise ValueError("mode must be initial or incremental")
        return iter(sorted(records, key=lambda record: (record.source_updated_at, record.object_id, record.event_type)))

    def ensure_globex_test_account(self) -> Dict[str, Any]:
        """Create or confirm only the explicitly marked fictional Globex Account."""
        escaped = TEST_WEBSITE.replace("'", "\\'")
        soql = (
            "SELECT Id, Name, Website, Description, LastModifiedDate, IsDeleted "
            "FROM Account WHERE Website = '%s'" % escaped
        )
        matches = [record for record, _ in self._query_all(soql) if record.get("IsDeleted") is not True]
        if matches:
            safe = [record for record in matches if record.get("Description") == TEST_MARKER]
            if len(safe) != len(matches) or len(safe) != 1:
                raise ConfigurationError("Salesforce test Website collides with an unmarked or duplicate Account")
            return self._get_record("Account", str(safe[0]["Id"]))[0]
        url = "%s/sobjects/Account/" % self.api_root
        created = self._request(
            "POST",
            url,
            document={
                "Name": TEST_NAME,
                "Website": TEST_WEBSITE,
                "Industry": "Healthcare",
                "BillingCountry": "United States",
                "Description": TEST_MARKER,
            },
            expected_statuses=(201,),
        )
        object_id = created.get("id")
        if not isinstance(object_id, str):
            raise ApiRequestError("POST", url, 201, "Salesforce create response has no id")
        return self._get_record("Account", object_id)[0]

    def update_globex_test_name(self, object_id: str, new_name: str) -> Dict[str, Any]:
        """Update the test Account only after verifying its ownership marker."""
        current, _ = self._get_record("Account", object_id)
        if current.get("Description") != TEST_MARKER or current.get("Website") != TEST_WEBSITE:
            raise ConfigurationError("refusing to modify an unmarked Salesforce Account")
        url = "%s/sobjects/Account/%s" % (self.api_root, quote(object_id))
        self._request(
            "PATCH", url, document={"Name": new_name}, safe_to_retry=True, expected_statuses=(204,)
        )
        return self._get_record("Account", object_id)[0]
