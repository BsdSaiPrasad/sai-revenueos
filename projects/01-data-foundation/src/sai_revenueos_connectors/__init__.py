"""P1.6 live Salesforce and HubSpot connector interfaces."""

from .http import (
    ApiRequestError,
    ConfigurationError,
    ConnectorError,
    HttpResponse,
    JsonHttpClient,
    RequestTrace,
    RetryPolicy,
)
from .hubspot import HubSpotAccessToken, HubSpotConnector, load_hubspot_token
from .models import StreamSyncResult, SyncRunResult, VendorRecord
from .runner import LiveIngestionRunner
from .salesforce import SalesforceConnector, SalesforceOAuthFile, StaticSalesforceToken

__all__ = [
    "ApiRequestError",
    "ConfigurationError",
    "ConnectorError",
    "HttpResponse",
    "HubSpotAccessToken",
    "HubSpotConnector",
    "JsonHttpClient",
    "LiveIngestionRunner",
    "RequestTrace",
    "RetryPolicy",
    "SalesforceConnector",
    "SalesforceOAuthFile",
    "StaticSalesforceToken",
    "StreamSyncResult",
    "SyncRunResult",
    "VendorRecord",
    "load_hubspot_token",
]
