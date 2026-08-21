"""Tiny projection sample used by docs and tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .contracts import CANVAS_QUERY_SCHEMA, SOURCE_FACTS_SCHEMA, build_projection_prompt
from .validation import materialize_canvas_model

SAMPLE_SOURCE_FACTS: Dict[str, Any] = {
    "schema": SOURCE_FACTS_SCHEMA,
    "version": "0.1.0",
    "repo": {
        "name": "sample-js-app",
        "root": "/workspace/sample-js-app",
        "summary": {
            "source_files": 9,
            "test_files": 2,
            "routes": 2,
        },
    },
    "facts": [
        {
            "id": "fact:file:src/routes/checkout.js",
            "kind": "file_chunk",
            "subject": "src/routes/checkout.js",
            "summary": "Checkout route exposes /checkout and imports checkout orchestration.",
            "attributes": {
                "path": "src/routes/checkout.js",
                "role": "route",
                "routes": [{"path": "/checkout", "method": None}],
                "imports": ["src/checkout.js"],
            },
            "evidence": [{"path": "src/routes/checkout.js"}],
            "confidence": 0.95,
        },
        {
            "id": "fact:file:src/checkout.js",
            "kind": "file_chunk",
            "subject": "src/checkout.js",
            "summary": "Checkout orchestration calculates totals and submits orders.",
            "attributes": {
                "path": "src/checkout.js",
                "role": "domain_flow",
                "exports": [
                    "calculateSubtotal",
                    "createCheckoutSummary",
                    "submitCheckout",
                ],
                "imports": [
                    "src/actions/apply-discount.js",
                    "src/actions/submit-order.js",
                    "src/services/inventory.js",
                ],
            },
            "evidence": [{"path": "src/checkout.js"}],
            "confidence": 0.95,
        },
        {
            "id": "fact:test:checkout",
            "kind": "test_chunk",
            "subject": "checkout tests",
            "summary": "Checkout unit and integration tests cover checkout behavior.",
            "attributes": {
                "paths": [
                    "checkout.test.js",
                    "tests/checkout.integration.test.js",
                ]
            },
            "evidence": [
                {"path": "checkout.test.js"},
                {"path": "tests/checkout.integration.test.js"},
            ],
            "confidence": 0.9,
        },
    ],
    "warnings": [],
}


SAMPLE_LLM_CANVAS_QUERY: Dict[str, Any] = {
    "schema": CANVAS_QUERY_SCHEMA,
    "version": "0.1.0",
    "mode": "llm-assisted",
    "intent": "Show checkout as a human-readable AgentCanvas journey with tests.",
    "operations": [
        {
            "op": "upsert_node",
            "node": {
                "id": "route:/checkout",
                "type": "route",
                "label": "Checkout route",
                "path": "src/routes/checkout.js",
                "data": {
                    "flow_role": "entrypoint",
                    "journey_step": {
                        "kind": "When",
                        "text": "Someone submits checkout.",
                        "provenance_fact_ids": ["fact:file:src/routes/checkout.js"],
                    },
                },
            },
            "fact_ids": ["fact:file:src/routes/checkout.js"],
            "confidence": 0.95,
            "rationale": "The route fact identifies /checkout.",
        },
        {
            "op": "upsert_node",
            "node": {
                "id": "flow:checkout",
                "type": "flow",
                "label": "Checkout orchestration",
                "path": "src/checkout.js",
                "data": {
                    "flow_role": "domain_logic",
                    "journey": {
                        "title": "Checkout",
                        "steps": [
                            {
                                "kind": "When",
                                "text": "Someone submits checkout.",
                                "provenance_fact_ids": ["fact:file:src/routes/checkout.js"],
                            },
                            {
                                "kind": "Do",
                                "text": "Calculate totals and submit the order.",
                                "provenance_fact_ids": ["fact:file:src/checkout.js"],
                            },
                        ],
                    },
                },
            },
            "fact_ids": ["fact:file:src/checkout.js"],
            "confidence": 0.95,
            "rationale": "The checkout fact describes totals and order submission.",
        },
        {
            "op": "upsert_node",
            "node": {
                "id": "tests:checkout",
                "type": "test",
                "label": "Checkout tests",
                "path": "checkout.test.js",
                "data": {
                    "paths": [
                        "checkout.test.js",
                        "tests/checkout.integration.test.js",
                    ]
                },
            },
            "fact_ids": ["fact:test:checkout"],
            "confidence": 0.9,
            "rationale": "The test fact lists checkout coverage.",
        },
        {
            "op": "upsert_edge",
            "edge": {
                "source": "route:/checkout",
                "target": "flow:checkout",
                "kind": "delegates_to",
            },
            "fact_ids": [
                "fact:file:src/routes/checkout.js",
                "fact:file:src/checkout.js",
            ],
            "confidence": 0.9,
            "rationale": "The route file imports the checkout orchestration file.",
        },
        {
            "op": "upsert_edge",
            "edge": {
                "source": "tests:checkout",
                "target": "flow:checkout",
                "kind": "covers",
            },
            "fact_ids": ["fact:test:checkout", "fact:file:src/checkout.js"],
            "confidence": 0.85,
            "rationale": "Checkout tests and checkout flow facts share the same subject.",
        },
    ],
    "warnings": [],
}


def build_sample_projection() -> Dict[str, Any]:
    """Return facts, prompt contract, LLM-style response, and canvas model."""

    facts = deepcopy(SAMPLE_SOURCE_FACTS)
    query = deepcopy(SAMPLE_LLM_CANVAS_QUERY)
    prompt_contract = build_projection_prompt(facts)
    canvas_model = materialize_canvas_model(
        query,
        facts["repo"],
        source_facts=facts,
    )
    return {
        "source_facts": facts,
        "prompt_contract": prompt_contract,
        "llm_canvas_query": query,
        "canvas_model": canvas_model,
    }
