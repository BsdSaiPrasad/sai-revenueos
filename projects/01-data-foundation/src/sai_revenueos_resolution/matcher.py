"""Deterministic and explainable Account and Person candidate matching."""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from sai_revenueos_identity import IdentityStore

from .models import CandidateMatch, StagedIdentityRecord
from .normalization import (
    normalize_company_name,
    normalize_domain,
    normalize_email,
    normalize_person_name,
    token_similarity,
)
from .policy import EntityMatchPolicy, ResolutionPolicy


class DeterministicMatcher:
    """Generate canonical candidates from staged rows with approved mappings.

    A candidate profile is not a second canonical store. It is the latest P1.7
    row for a SourceRecord that already has an active P1.2 crosswalk. This keeps
    matching evidence tied to real source provenance and existing identity truth.
    """

    def __init__(self, policy: Optional[ResolutionPolicy] = None) -> None:
        self.policy = policy or ResolutionPolicy()

    @staticmethod
    def _account_features(
        source: StagedIdentityRecord,
        reference: StagedIdentityRecord,
        rule: EntityMatchPolicy,
    ) -> Tuple[float, Dict[str, object]]:
        left_domain, right_domain = normalize_domain(source.domain), normalize_domain(reference.domain)
        left_name = normalize_company_name(source.name)
        right_name = normalize_company_name(reference.name)
        similarity = token_similarity(left_name, right_name)
        weights = rule.features
        score = 0.0
        features: Dict[str, object] = {
            "exact_domain": bool(left_domain and left_domain == right_domain),
            "exact_name": bool(left_name and left_name == right_name),
            "name_similarity": round(similarity, 4),
            "exact_country": bool(
                source.country and reference.country
                and source.country.strip().casefold() == reference.country.strip().casefold()
            ),
            "conflicting_domain": bool(left_domain and right_domain and left_domain != right_domain),
        }
        if features["exact_domain"]:
            score += weights["exact_domain"]
        if features["exact_name"]:
            score += weights["exact_name"]
        elif similarity >= rule.similar_name_minimum:
            score += weights["similar_name"]
        if features["exact_country"]:
            score += weights["exact_country"]
        if features["conflicting_domain"]:
            score += weights["conflicting_domain"]
        return max(0.0, min(1.0, round(score, 6))), features

    @staticmethod
    def _person_features(
        source: StagedIdentityRecord,
        reference: StagedIdentityRecord,
        rule: EntityMatchPolicy,
        source_employer: Optional[str],
        reference_employer: Optional[str],
    ) -> Tuple[float, Dict[str, object]]:
        left_email, right_email = normalize_email(source.email), normalize_email(reference.email)
        left_name = normalize_person_name(source.name)
        right_name = normalize_person_name(reference.name)
        similarity = token_similarity(left_name, right_name)
        weights = rule.features
        score = 0.0
        features: Dict[str, object] = {
            "exact_email": bool(left_email and left_email == right_email),
            "conflicting_email": bool(left_email and right_email and left_email != right_email),
            "exact_name": bool(left_name and left_name == right_name),
            "name_similarity": round(similarity, 4),
            "same_employer": bool(source_employer and source_employer == reference_employer),
        }
        if features["exact_email"]:
            score += weights["exact_email"]
        if features["exact_name"]:
            score += weights["exact_name"]
        elif similarity >= rule.similar_name_minimum:
            score += weights["similar_name"]
        if features["same_employer"]:
            score += weights["same_employer"]
        if features["conflicting_email"]:
            score += weights["conflicting_email"]
        return max(0.0, min(1.0, round(score, 6))), features

    @staticmethod
    def _blocked(source: StagedIdentityRecord, reference: StagedIdentityRecord) -> bool:
        if source.entity_type == "Account":
            return bool(
                normalize_domain(source.domain)
                and normalize_domain(source.domain) == normalize_domain(reference.domain)
            ) or bool(
                normalize_company_name(source.name)
                and normalize_company_name(source.name) == normalize_company_name(reference.name)
            )
        return bool(
            normalize_email(source.email)
            and normalize_email(source.email) == normalize_email(reference.email)
        ) or bool(
            normalize_person_name(source.name)
            and normalize_person_name(source.name) == normalize_person_name(reference.name)
        )

    @staticmethod
    def _employer_mapping(
        record: StagedIdentityRecord,
        records: Iterable[StagedIdentityRecord],
        identity_store: IdentityStore,
    ) -> Optional[str]:
        if not record.employer_source_object_id:
            return None
        for company in records:
            if (
                company.entity_type == "Account"
                and company.source_system == record.source_system
                and company.source_tenant == record.source_tenant
                and company.source_object_id == record.employer_source_object_id
            ):
                mapping = identity_store.active_mapping_for_source(company.source_record_id)
                return None if mapping is None else str(mapping["canonical_entity_id"])
        return None

    def match(
        self,
        source: StagedIdentityRecord,
        records: Iterable[StagedIdentityRecord],
        identity_store: IdentityStore,
    ) -> List[CandidateMatch]:
        """Return ranked candidates without approving or activating a mapping."""
        all_records = tuple(records)
        rule = self.policy.entity(source.entity_type)
        source_employer = self._employer_mapping(source, all_records, identity_store)
        best: Dict[str, CandidateMatch] = {}
        for reference in all_records:
            if (
                reference.source_record_id == source.source_record_id
                or reference.entity_type != source.entity_type
                or reference.event_type != "upsert"
                or reference.is_deleted
                or not self._blocked(source, reference)
            ):
                continue
            mapping = identity_store.active_mapping_for_source(reference.source_record_id)
            if mapping is None or mapping["canonical_entity_type"] != source.entity_type:
                continue
            canonical_id = str(mapping["canonical_entity_id"])
            if source.entity_type == "Account":
                score, features = self._account_features(source, reference, rule)
            else:
                score, features = self._person_features(
                    source,
                    reference,
                    rule,
                    source_employer,
                    self._employer_mapping(reference, all_records, identity_store),
                )
            if score < rule.minimum_candidate_score:
                continue
            candidate = CandidateMatch(
                canonical_entity_id=canonical_id,
                score=score,
                reference_source_record_id=reference.source_record_id,
                features=features,
            )
            current = best.get(canonical_id)
            if current is None or (candidate.score, candidate.reference_source_record_id) > (
                current.score,
                current.reference_source_record_id,
            ):
                best[canonical_id] = candidate
        return sorted(
            best.values(),
            key=lambda item: (-item.score, item.canonical_entity_id),
        )
