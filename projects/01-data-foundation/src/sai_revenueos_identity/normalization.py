"""Validate and normalize source-system identity without losing provenance.

A source object is unique only within its four-part namespace: system, tenant,
object type, and object ID. RevenueOS stores both the submitted values and a
carefully normalized comparison form. Vendor object IDs stay case-sensitive by
default because changing their meaning could link the wrong company or person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict

from .errors import ValidationError


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_COMPONENT_LENGTH = 255


@dataclass(frozen=True)
class SourceIdentity:
    """Original and comparison forms of the four-part source identity key.

    For example, a Salesforce Account for Globex Health keeps the exact tenant and
    object ID supplied by Salesforce while controlled vocabulary such as the system
    name and object type can be compared case-insensitively.
    """

    source_system: str
    source_tenant: str
    source_object_type: str
    source_object_id: str
    normalized_source_system: str
    normalized_source_tenant: str
    normalized_source_object_type: str
    normalized_source_object_id: str


def _exact_identifier(value: str) -> str:
    """Preserve vendor identifier case and punctuation after trimming."""

    return value.strip()


# Salesforce IDs can be case-sensitive in their 15-character form. HubSpot IDs are
# commonly numeric, but preserving the supplied value avoids inventing semantics.
# New systems may register a documented rule without changing existing identities.
SOURCE_ID_NORMALIZERS: Dict[str, Callable[[str], str]] = {
    "salesforce": _exact_identifier,
    "hubspot": _exact_identifier,
}


def register_source_id_normalizer(
    source_system: str,
    normalizer: Callable[[str], str],
) -> None:
    """Register one documented object-ID normalizer for a future source system.

    The registry rejects replacement of an existing rule. Silently changing how
    Salesforce or HubSpot IDs compare could split or combine existing identities.
    """

    system = _validate_component("source_system", source_system).casefold()
    if system in SOURCE_ID_NORMALIZERS:
        raise ValidationError("a source ID normalizer is already registered for %s" % system)
    SOURCE_ID_NORMALIZERS[system] = normalizer


def _validate_component(name: str, value: str) -> str:
    """Return a trimmed, safe key component or raise ``ValidationError``."""
    if not isinstance(value, str):
        raise ValidationError("%s must be a string" % name)
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError("%s cannot be empty" % name)
    if len(trimmed) > _MAX_COMPONENT_LENGTH:
        raise ValidationError("%s exceeds %d characters" % (name, _MAX_COMPONENT_LENGTH))
    if _CONTROL_CHARACTERS.search(trimmed):
        raise ValidationError("%s cannot contain control characters" % name)
    return trimmed


def normalize_source_identity(
    source_system: str,
    source_tenant: str,
    source_object_type: str,
    source_object_id: str,
) -> SourceIdentity:
    """Validate and normalize the approved four-part source identity key.

    System and object-type codes are controlled, case-insensitive vocabulary.
    Tenant and object identifiers retain vendor-defined case by default.

    Args:
        source_system: Source product, for example ``Salesforce`` or ``HubSpot``.
        source_tenant: Independent source namespace, such as ``globex-prod``.
        source_object_type: Vendor object type, such as ``Account``.
        source_object_id: The exact vendor-provided object identifier.

    Returns:
        A ``SourceIdentity`` containing original values for provenance and
        normalized values for the database uniqueness comparison.

    Raises:
        ValidationError: If a component is empty, too long, not text, contains a
        control character, or normalizes to an invalid value.
    """

    original_system = _validate_component("source_system", source_system)
    original_tenant = _validate_component("source_tenant", source_tenant)
    original_type = _validate_component("source_object_type", source_object_type)
    original_id = _validate_component("source_object_id", source_object_id)

    # Only controlled vocabulary is case-folded. Tenant and object IDs retain
    # vendor-defined case so records are never combined on an invented rule.
    normalized_system = original_system.casefold()
    normalized_type = original_type.casefold()
    id_normalizer = SOURCE_ID_NORMALIZERS.get(normalized_system, _exact_identifier)
    normalized_id = id_normalizer(original_id)
    normalized_id = _validate_component("normalized_source_object_id", normalized_id)

    return SourceIdentity(
        source_system=original_system,
        source_tenant=original_tenant,
        source_object_type=original_type,
        source_object_id=original_id,
        normalized_source_system=normalized_system,
        normalized_source_tenant=original_tenant,
        normalized_source_object_type=normalized_type,
        normalized_source_object_id=normalized_id,
    )
