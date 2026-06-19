"""Provider-agnostic projection helpers for AgentCanvas.

The projection layer does not call an LLM itself. It prepares facts, prompts,
schemas, deterministic fallbacks, and validators that any calling agent can use.
"""

from .contracts import (
    CANVAS_QUERY_SCHEMA,
    CANVAS_QUERY_JSON_SCHEMA,
    PROJECTION_CONTRACT_SCHEMA,
    PROJECTION_CONTRACT_JSON_SCHEMA,
    SOURCE_FACTS_SCHEMA,
    SOURCE_FACTS_JSON_SCHEMA,
    build_projection_contract,
    build_projection_prompt,
    facts_from_workflow_ir,
    normalize_fact_bundle,
)
from .heuristic import heuristic_project
from .validation import (
    ProjectionValidationError,
    materialize_canvas_model,
    validate_canvas_model,
    validate_canvas_query,
)

__all__ = [
    "CANVAS_QUERY_SCHEMA",
    "CANVAS_QUERY_JSON_SCHEMA",
    "PROJECTION_CONTRACT_SCHEMA",
    "PROJECTION_CONTRACT_JSON_SCHEMA",
    "SOURCE_FACTS_SCHEMA",
    "SOURCE_FACTS_JSON_SCHEMA",
    "ProjectionValidationError",
    "build_projection_contract",
    "build_projection_prompt",
    "facts_from_workflow_ir",
    "heuristic_project",
    "materialize_canvas_model",
    "normalize_fact_bundle",
    "validate_canvas_model",
    "validate_canvas_query",
]
