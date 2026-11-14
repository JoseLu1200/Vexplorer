"""A/B/C/D method comparison harness (protocol: docs/COMPARATIVA_METODOS.md)."""

from .freeze import FreezeToken, verify_freeze
from .manifest import (
    DevelopmentManifestReader,
    ManifestReader,
    PlankAssemblyManifestReader,
)
from .methods import (
    AdapterRequest,
    AdapterResponse,
    PrecedentIndex,
    RulesMethod,
    build_methods,
)
from .model import ComparisonError, ModelVariantsDisabled, ReferenceNotFrozen, RunLimits
from .report import render_markdown
from .runner import Clock, execute_run, score_run

__all__ = [
    "AdapterRequest", "AdapterResponse", "Clock", "ComparisonError", "DevelopmentManifestReader",
    "FreezeToken", "ManifestReader", "ModelVariantsDisabled", "PlankAssemblyManifestReader",
    "PrecedentIndex", "ReferenceNotFrozen", "RulesMethod", "RunLimits", "build_methods",
    "execute_run", "render_markdown", "score_run", "verify_freeze",
]
