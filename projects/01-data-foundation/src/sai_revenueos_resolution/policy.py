"""Load and validate the approved P1.8 deterministic resolution policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .errors import ResolutionValidationError


PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = PROJECT / "contracts/identity-resolution-policy.v1.json"


@dataclass(frozen=True)
class EntityMatchPolicy:
    """Weights and thresholds for one canonical entity type."""

    entity_type: str
    minimum_candidate_score: float
    blocking_fields: Tuple[str, ...]
    features: Mapping[str, float]
    similar_name_minimum: float


class ResolutionPolicy:
    """Validated P1.8 policy used by matching, review, and survivorship."""

    def __init__(self, path: Path = DEFAULT_POLICY_PATH) -> None:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResolutionValidationError("identity resolution policy cannot be loaded") from exc
        self._validate(document)
        self.document = document
        self.contract_version = str(document["contract_version"])
        self.input_models = dict(document["input_models"])
        self.human_approval_required = bool(
            document["decision_policy"]["human_approval_required_for_every_new_crosswalk"]
        )
        self.automatic_merge = bool(document["decision_policy"]["automatic_merge"])
        self.review_owner_role = str(document["review"]["identity_owner_role"])
        self.field_extractors = tuple(document["survivorship"]["field_extractors"])

    @staticmethod
    def _validate(document: Mapping[str, Any]) -> None:
        if document.get("contract_name") != "identity-resolution-policy":
            raise ResolutionValidationError("unexpected resolution policy name")
        if document.get("contract_version") != "1.0.0":
            raise ResolutionValidationError("unsupported resolution policy version")
        if set(document.get("input_models", {})) != {"Account", "Person"}:
            raise ResolutionValidationError("P1.8 input models must cover Account and Person")
        matching = document.get("matching")
        if not isinstance(matching, Mapping) or set(matching) != {"Account", "Person"}:
            raise ResolutionValidationError("matching policy must cover Account and Person")
        for entity_type, rule in matching.items():
            if not isinstance(rule, Mapping):
                raise ResolutionValidationError("matching rule must be an object")
            threshold = rule.get("minimum_candidate_score")
            if not isinstance(threshold, (int, float)) or not 0 < float(threshold) <= 1:
                raise ResolutionValidationError("candidate threshold must be between zero and one")
            features = rule.get("features")
            if not isinstance(features, Mapping) or not features:
                raise ResolutionValidationError("matching features are required for %s" % entity_type)
            if not all(isinstance(value, (int, float)) for value in features.values()):
                raise ResolutionValidationError("feature weights must be numeric")
        decision = document.get("decision_policy", {})
        if not decision.get("human_approval_required_for_every_new_crosswalk"):
            raise ResolutionValidationError("every P1.8 crosswalk must require human approval")
        if decision.get("automatic_merge") or decision.get("automatic_crosswalk_activation"):
            raise ResolutionValidationError("P1.8 cannot automatically merge or activate mappings")
        survivorship = document.get("survivorship", {})
        if survivorship.get("authority_contract") != "field-authority-policy.v1.json":
            raise ResolutionValidationError("P1.8 survivorship must reuse P1.4 authority")
        if survivorship.get("matching_score_selects_field_value"):
            raise ResolutionValidationError("matching scores cannot select surviving field values")
        boundaries = document.get("boundaries", {})
        if boundaries.get("p1_9_canonical_models"):
            raise ResolutionValidationError("P1.8 cannot implement P1.9 canonical models")

    def entity(self, entity_type: str) -> EntityMatchPolicy:
        """Return the approved rule for Account or Person."""
        try:
            rule = self.document["matching"][entity_type]
        except KeyError as exc:
            raise ResolutionValidationError("unsupported identity entity type") from exc
        return EntityMatchPolicy(
            entity_type=entity_type,
            minimum_candidate_score=float(rule["minimum_candidate_score"]),
            blocking_fields=tuple(str(value) for value in rule["blocking_fields"]),
            features={str(name): float(value) for name, value in rule["features"].items()},
            similar_name_minimum=float(rule["similar_name_minimum"]),
        )

    def extractors_for(self, entity_type: str, source_system: str) -> Sequence[Mapping[str, Any]]:
        """Return governed field extractors for one entity and source system."""
        return tuple(
            extractor for extractor in self.field_extractors
            if extractor["entity_type"] == entity_type
            and extractor["source_system"] == source_system.casefold()
        )

    def as_dict(self) -> Dict[str, Any]:
        """Return a defensive copy for validation and documentation."""
        return json.loads(json.dumps(self.document))
