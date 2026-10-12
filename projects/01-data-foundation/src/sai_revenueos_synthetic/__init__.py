"""Deterministic P1.5 synthetic go-to-market dataset generation."""

from .generator import GenerationConfig, SyntheticDataset, generate_dataset
from .validation import ValidationReport, validate_dataset
from .writer import write_dataset

__all__ = [
    "GenerationConfig",
    "SyntheticDataset",
    "ValidationReport",
    "generate_dataset",
    "validate_dataset",
    "write_dataset",
]
