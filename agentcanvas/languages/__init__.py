"""Language extraction modules for AgentCanvas.

Language modules provide grounding facts, chunks, and provenance for the shared
projection layer. They are intentionally pluggable: the core canvas mapper should
not need to know whether a fact came from JS/TS, Python, or a future language.
"""

from . import dart_lang, go_lang, js_ts, kotlin_lang, php_lang, python_lang, ruby_lang, swift_lang

__all__ = [
    "dart_lang",
    "go_lang",
    "js_ts",
    "kotlin_lang",
    "php_lang",
    "python_lang",
    "ruby_lang",
    "swift_lang",
]
