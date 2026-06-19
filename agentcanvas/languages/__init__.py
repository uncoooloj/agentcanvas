"""Language extraction modules for AgentCanvas.

Language modules provide grounding facts, chunks, and provenance for the shared
projection layer. They are intentionally pluggable: the core canvas mapper should
not need to know whether a fact came from JS/TS, Python, or a future language.
"""

from . import js_ts, python_lang

__all__ = ["js_ts", "python_lang"]
