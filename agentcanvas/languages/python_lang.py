"""Python source fact extraction for AgentCanvas.

The extractor is intentionally standalone today: it emits language-neutral fact
dictionaries that can be adapted into the shared workflow IR once the indexer has
a module interface.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Set, Union

LANGUAGE = "python"

HTTP_METHODS = {
    "delete": "DELETE",
    "get": "GET",
    "head": "HEAD",
    "options": "OPTIONS",
    "patch": "PATCH",
    "post": "POST",
    "put": "PUT",
    "trace": "TRACE",
}
HTTP_ROUTE_DECORATORS = set(HTTP_METHODS) | {
    "api_route",
    "route",
    "websocket",
    "websocket_route",
}
DJANGO_ROUTE_CALLS = {"path", "re_path", "url"}
DJANGO_HTTP_DECORATORS = {
    "require_GET": ["GET"],
    "require_POST": ["POST"],
    "require_safe": ["GET", "HEAD"],
}
CALL_ROUTE_HELPERS = {"add_api_route", "add_url_rule"}

PathLike = Union[str, Path]


def extract_source_facts(path: PathLike, source: Optional[str] = None) -> Dict[str, Any]:
    """Extract language-neutral facts from a Python source file or source string."""

    display_path = _display_path(path)
    errors: List[Dict[str, Any]] = []
    if source is None:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            facts = [
                _file_fact(display_path, "", readable=False),
                {
                    "id": _stable_id("read_error", display_path, 1, type(exc).__name__),
                    "type": "read_error",
                    "kind": type(exc).__name__,
                    "language": LANGUAGE,
                    "message": str(exc),
                    "file": display_path,
                    "line": 1,
                    "provenance": {"path": display_path, "line": 1},
                },
            ]
            return {
                "language": LANGUAGE,
                "path": display_path,
                "facts": facts,
                "summary": _summary(facts),
                "errors": [facts[-1]],
            }

    facts = [_file_fact(display_path, source)]
    try:
        tree = ast.parse(source, filename=display_path)
    except SyntaxError as exc:
        error = _syntax_error_fact(display_path, exc)
        facts.append(error)
        errors.append(error)
        return {
            "language": LANGUAGE,
            "path": display_path,
            "facts": facts,
            "summary": _summary(facts),
            "errors": errors,
        }

    extractor = _PythonFactExtractor(display_path, source)
    facts.extend(extractor.extract(tree))
    return {
        "language": LANGUAGE,
        "path": display_path,
        "facts": facts,
        "summary": _summary(facts),
        "errors": errors,
    }


def extract_file(path: PathLike) -> Dict[str, Any]:
    """Read and extract facts from a Python file."""

    return extract_source_facts(path)


class _PythonFactExtractor(ast.NodeVisitor):
    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.source = source
        self.lines = source.splitlines()
        self.facts: List[Dict[str, Any]] = []
        self.seen_ids: Set[str] = set()
        self.scope: List[str] = []

    def extract(self, tree: ast.AST) -> List[Dict[str, Any]]:
        self.visit(tree)
        return self.facts

    def add_fact(self, fact: Dict[str, Any]) -> None:
        fact.setdefault("language", LANGUAGE)
        provenance = fact.get("provenance") or {"path": self.path, "line": 1}
        fact.setdefault("file", provenance.get("path", self.path))
        fact.setdefault("line", provenance.get("line", 1))
        fact.setdefault(
            "id",
            _stable_id(
                str(fact.get("type", "fact")),
                self.path,
                int(fact.get("line") or 1),
                str(fact.get("name") or fact.get("qualified_name") or fact.get("path") or ""),
            ),
        )
        if fact["id"] in self.seen_ids:
            return
        self.seen_ids.add(fact["id"])
        self.facts.append(fact)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self.add_fact(
                {
                    "id": _stable_id("import", self.path, node.lineno, alias.name),
                    "type": "import",
                    "kind": "import",
                    "module": alias.name,
                    "imported": alias.name,
                    "local_name": local_name,
                    "provenance": self.provenance(node),
                }
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * int(node.level or 0) + (node.module or "")
        for alias in node.names:
            imported = alias.name
            local_name = alias.asname or imported
            specifier = f"{module}.{imported}" if module and imported != "*" else module or imported
            self.add_fact(
                {
                    "id": _stable_id("import", self.path, node.lineno, specifier),
                    "type": "import",
                    "kind": "from",
                    "module": module,
                    "imported": imported,
                    "local_name": local_name,
                    "level": int(node.level or 0),
                    "provenance": self.provenance(node),
                }
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "async_function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self.qualified_name(node.name)
        decorators = self.emit_decorators(node.decorator_list, qualified_name, "class")
        for decorator in node.decorator_list:
            self.visit(decorator)

        self.add_fact(
            {
                "id": _stable_id("symbol", self.path, node.lineno, qualified_name),
                "type": "symbol",
                "kind": "class",
                "name": node.name,
                "qualified_name": qualified_name,
                "scope": self.scope_name(),
                "decorators": decorators,
                "bases": [self.source_segment(base) for base in node.bases],
                "provenance": self.provenance(node),
            }
        )

        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        function = self.call_name(node)
        route = self.route_from_call(node)
        if route:
            self.add_fact(route)

        self.add_fact(
            {
                "id": _stable_id("call", self.path, node.lineno, function or self.source_segment(node.func)),
                "type": "call",
                "kind": "function_call",
                "function": function or "<dynamic>",
                "scope": self.scope_name(),
                "args": [self.literal_preview(arg) for arg in node.args[:5]],
                "arg_count": len(node.args),
                "keywords": [keyword.arg or "**" for keyword in node.keywords],
                "provenance": self.provenance(node),
            }
        )
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.visit_if_chain(node, "if", node.lineno)

    def _visit_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        kind: str,
    ) -> None:
        qualified_name = self.qualified_name(node.name)
        decorators = self.emit_decorators(node.decorator_list, qualified_name, kind)
        for decorator in node.decorator_list:
            self.visit(decorator)

        self.add_fact(
            {
                "id": _stable_id("symbol", self.path, node.lineno, qualified_name),
                "type": "symbol",
                "kind": kind,
                "name": node.name,
                "qualified_name": qualified_name,
                "scope": self.scope_name(),
                "parameters": self.parameters(node.args),
                "returns": self.source_segment(node.returns) if node.returns else None,
                "decorators": decorators,
                "provenance": self.provenance(node),
            }
        )

        self.visit_arguments(node.args)
        if node.returns:
            self.visit(node.returns)

        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    def emit_decorators(
        self,
        decorators: Sequence[ast.expr],
        target: str,
        target_kind: str,
    ) -> List[str]:
        expressions = []
        for decorator in decorators:
            expression = self.source_segment(decorator)
            expressions.append(expression)
            decorator_name = self.decorator_name(decorator)
            metadata = self.decorator_metadata(decorator)
            self.add_fact(
                {
                    "id": _stable_id("decorator", self.path, _line(decorator), f"{target}:{expression}"),
                    "type": "decorator",
                    "kind": metadata.get("kind", "decorator"),
                    "name": decorator_name,
                    "expression": expression,
                    "target": target,
                    "target_kind": target_kind,
                    "methods": metadata.get("methods", []),
                    "route_path": metadata.get("route_path"),
                    "provenance": self.provenance(decorator),
                }
            )

            route = self.route_from_decorator(decorator, target, target_kind, expression)
            if route:
                self.add_fact(route)
        return expressions

    def decorator_metadata(self, decorator: ast.expr) -> Dict[str, Any]:
        call = decorator if isinstance(decorator, ast.Call) else None
        func = call.func if call else decorator
        name = self.decorator_name(decorator)
        leaf = name.rsplit(".", 1)[-1] if name else ""
        if call and leaf == "require_http_methods":
            return {"kind": "http_method_decorator", "methods": self.string_list(call.args[0]) if call.args else []}
        if leaf in DJANGO_HTTP_DECORATORS:
            return {"kind": "http_method_decorator", "methods": DJANGO_HTTP_DECORATORS[leaf]}
        if isinstance(func, ast.Attribute) and func.attr.lower() in HTTP_ROUTE_DECORATORS:
            attr = func.attr.lower()
            return {
                "kind": "route_decorator",
                "methods": self.methods_for_route_decorator(attr, call),
                "route_path": self.first_string_arg(call),
            }
        return {"kind": "decorator"}

    def route_from_decorator(
        self,
        decorator: ast.expr,
        target: str,
        target_kind: str,
        expression: str,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            return None
        attr = decorator.func.attr.lower()
        if attr not in HTTP_ROUTE_DECORATORS:
            return None
        route_path = self.first_string_arg(decorator)
        if not route_path:
            return None

        methods = self.methods_for_route_decorator(attr, decorator)
        router = self.dotted_name(decorator.func.value)
        line = _line(decorator)
        return {
            "id": _stable_id("route", self.path, line, f"{target}:{route_path}:{','.join(methods)}"),
            "type": "route",
            "kind": "http_route",
            "framework": self.framework_for_route_decorator(attr),
            "path": route_path,
            "methods": methods,
            "handler": target,
            "handler_kind": target_kind,
            "router": router,
            "source": "decorator",
            "decorator": expression,
            "provenance": self.provenance(decorator),
        }

    def route_from_call(self, call: ast.Call) -> Optional[Dict[str, Any]]:
        name = self.call_name(call)
        leaf = name.rsplit(".", 1)[-1] if name else ""
        route_path = self.first_string_arg(call)
        if not route_path:
            return None

        if leaf in DJANGO_ROUTE_CALLS:
            view = self.source_segment(call.args[1]) if len(call.args) > 1 else None
            return {
                "id": _stable_id("route", self.path, _line(call), f"django:{route_path}:{view or ''}"),
                "type": "route",
                "kind": "url_pattern",
                "framework": "django",
                "path": route_path,
                "methods": [],
                "handler": view,
                "source": "call",
                "call": name,
                "name": self.keyword_string(call, "name"),
                "provenance": self.provenance(call),
            }

        if leaf in CALL_ROUTE_HELPERS:
            methods = self.keyword_string_list(call, "methods")
            handler = self.keyword_expression(call, "endpoint") or self.keyword_expression(call, "view_func")
            if handler is None and len(call.args) > 1:
                handler = self.source_segment(call.args[1])
            if leaf == "add_url_rule" and handler is None and len(call.args) > 2:
                handler = self.source_segment(call.args[2])
            return {
                "id": _stable_id("route", self.path, _line(call), f"{leaf}:{route_path}:{handler or ''}"),
                "type": "route",
                "kind": "http_route",
                "framework": "fastapi_or_flask",
                "path": route_path,
                "methods": methods,
                "handler": handler,
                "source": "call",
                "call": name,
                "provenance": self.provenance(call),
            }

        return None

    def methods_for_route_decorator(self, attr: str, call: ast.Call) -> List[str]:
        if attr in HTTP_METHODS:
            return [HTTP_METHODS[attr]]
        if attr in {"websocket", "websocket_route"}:
            return ["WEBSOCKET"]
        return self.keyword_string_list(call, "methods")

    def framework_for_route_decorator(self, attr: str) -> str:
        if attr in {"api_route", "websocket", "websocket_route"}:
            return "fastapi"
        if attr == "route":
            return "flask_or_fastapi"
        return "fastapi_or_flask"

    def visit_if_chain(self, node: ast.If, kind: str, chain_line: int) -> None:
        condition = self.source_segment(node.test)
        self.add_fact(
            {
                "id": _stable_id("branch", self.path, node.lineno, f"{kind}:{condition}"),
                "type": "branch",
                "kind": kind,
                "condition": condition,
                "scope": self.scope_name(),
                "chain_id": _stable_id("branch_chain", self.path, chain_line, ""),
                "provenance": self.provenance(node),
            }
        )
        self.visit(node.test)
        for statement in node.body:
            self.visit(statement)

        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self.visit_if_chain(node.orelse[0], "elif", chain_line)
            return

        if node.orelse:
            else_line = self.else_line(node)
            self.add_fact(
                {
                    "id": _stable_id("branch", self.path, else_line, "else"),
                    "type": "branch",
                    "kind": "else",
                    "condition": None,
                    "scope": self.scope_name(),
                    "chain_id": _stable_id("branch_chain", self.path, chain_line, ""),
                    "provenance": self.provenance_from_line(else_line),
                }
            )
            for statement in node.orelse:
                self.visit(statement)

    def visit_arguments(self, args: ast.arguments) -> None:
        for item in getattr(args, "posonlyargs", []):
            if item.annotation:
                self.visit(item.annotation)
        for item in args.args:
            if item.annotation:
                self.visit(item.annotation)
        for item in args.kwonlyargs:
            if item.annotation:
                self.visit(item.annotation)
        if args.vararg and args.vararg.annotation:
            self.visit(args.vararg.annotation)
        if args.kwarg and args.kwarg.annotation:
            self.visit(args.kwarg.annotation)
        for default in list(args.defaults) + [item for item in args.kw_defaults if item]:
            self.visit(default)

    def parameters(self, args: ast.arguments) -> List[str]:
        values: List[str] = []
        values.extend(item.arg for item in getattr(args, "posonlyargs", []))
        values.extend(item.arg for item in args.args)
        if args.vararg:
            values.append(f"*{args.vararg.arg}")
        values.extend(item.arg for item in args.kwonlyargs)
        if args.kwarg:
            values.append(f"**{args.kwarg.arg}")
        return values

    def decorator_name(self, decorator: ast.expr) -> str:
        if isinstance(decorator, ast.Call):
            return self.dotted_name(decorator.func) or self.source_segment(decorator.func)
        return self.dotted_name(decorator) or self.source_segment(decorator)

    def call_name(self, call: ast.Call) -> Optional[str]:
        return self.dotted_name(call.func)

    def dotted_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self.dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            return self.dotted_name(node.func)
        if isinstance(node, ast.Subscript):
            return self.dotted_name(node.value)
        return None

    def first_string_arg(self, call: ast.Call) -> Optional[str]:
        return self.string_value(call.args[0]) if call.args else None

    def keyword_string(self, call: ast.Call, name: str) -> Optional[str]:
        for keyword in call.keywords:
            if keyword.arg == name:
                return self.string_value(keyword.value)
        return None

    def keyword_string_list(self, call: ast.Call, name: str) -> List[str]:
        for keyword in call.keywords:
            if keyword.arg == name:
                return self.string_list(keyword.value)
        return []

    def keyword_expression(self, call: ast.Call, name: str) -> Optional[str]:
        for keyword in call.keywords:
            if keyword.arg == name:
                return self.source_segment(keyword.value)
        return None

    def string_value(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Str):
            return node.s
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def string_list(self, node: ast.AST) -> List[str]:
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.string_value(item) for item in node.elts]
            return [value for value in values if value]
        value = self.string_value(node)
        return [value] if value else []

    def literal_preview(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, int, float, bool)) or node.value is None:
                return node.value
        if isinstance(node, ast.Str):
            return node.s
        if isinstance(node, (ast.List, ast.Tuple)):
            values = [self.literal_preview(item) for item in node.elts[:5]]
            return values
        return self.source_segment(node)

    def qualified_name(self, name: str) -> str:
        return ".".join(self.scope + [name]) if self.scope else name

    def scope_name(self) -> Optional[str]:
        return ".".join(self.scope) if self.scope else None

    def source_segment(self, node: Optional[ast.AST]) -> str:
        if node is None:
            return ""
        get_source_segment = getattr(ast, "get_source_segment", None)
        if get_source_segment is not None:
            segment = get_source_segment(self.source, node)
            if segment:
                return _collapse(segment)
        unparse = getattr(ast, "unparse", None)
        if unparse is not None:
            try:
                return _collapse(unparse(node))
            except (AttributeError, TypeError, ValueError):
                pass
        fallback = self.fallback_expression(node)
        if fallback:
            return fallback
        return type(node).__name__

    def fallback_expression(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Call):
            function = self.source_segment(node.func)
            parts = [self.source_segment(arg) for arg in node.args]
            for keyword in node.keywords:
                value = self.source_segment(keyword.value)
                if keyword.arg:
                    parts.append(f"{keyword.arg}={value}")
                else:
                    parts.append(f"**{value}")
            return f"{function}({', '.join(parts)})"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self.dotted_name(node)
        if isinstance(node, ast.Str):
            return repr(node.s)
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.List):
            return "[" + ", ".join(self.source_segment(item) for item in node.elts) + "]"
        if isinstance(node, ast.Tuple):
            suffix = "," if len(node.elts) == 1 else ""
            return "(" + ", ".join(self.source_segment(item) for item in node.elts) + suffix + ")"
        if isinstance(node, ast.Set):
            return "{" + ", ".join(self.source_segment(item) for item in node.elts) + "}"
        name = self.dotted_name(node)
        if name:
            return name
        return None

    def provenance(self, node: ast.AST) -> Dict[str, Any]:
        line = _line(node)
        provenance: Dict[str, Any] = {"path": self.path, "line": line}
        end_line = getattr(node, "end_lineno", None)
        if end_line:
            provenance["end_line"] = int(end_line)
        column = getattr(node, "col_offset", None)
        if column is not None:
            provenance["column"] = int(column) + 1
        end_column = getattr(node, "end_col_offset", None)
        if end_column is not None:
            provenance["end_column"] = int(end_column) + 1
        return provenance

    def provenance_from_line(self, line: int) -> Dict[str, Any]:
        return {"path": self.path, "line": line}

    def else_line(self, node: ast.If) -> int:
        first_orelse_line = _line(node.orelse[0]) if node.orelse else _line(node)
        body_end = _node_end_line(node.body[-1]) if node.body else _line(node)
        start = max(body_end + 1, _line(node) + 1)
        end = min(first_orelse_line, len(self.lines))
        for line_number in range(start, end + 1):
            if re.match(r"\s*else\s*:", self.lines[line_number - 1]):
                return line_number
        return first_orelse_line


def _file_fact(path: str, source: str, readable: bool = True) -> Dict[str, Any]:
    line_count = len(source.splitlines()) if source else 0
    return {
        "id": _stable_id("file", path, 1, path),
        "type": "file",
        "kind": "source_file",
        "language": LANGUAGE,
        "path": path,
        "lines": line_count,
        "readable": readable,
        "file": path,
        "line": 1,
        "provenance": {"path": path, "line": 1, "end_line": max(line_count, 1)},
    }


def _syntax_error_fact(path: str, exc: SyntaxError) -> Dict[str, Any]:
    line = int(exc.lineno or 1)
    provenance: Dict[str, Any] = {"path": path, "line": line}
    if exc.offset:
        provenance["column"] = int(exc.offset)
    return {
        "id": _stable_id("parse_error", path, line, exc.msg),
        "type": "parse_error",
        "kind": "SyntaxError",
        "language": LANGUAGE,
        "message": exc.msg,
        "file": path,
        "line": line,
        "provenance": provenance,
    }


def _summary(facts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for fact in facts:
        fact_type = str(fact.get("type", "fact"))
        counts[fact_type] = counts.get(fact_type, 0) + 1
    return {"facts": len(facts), "by_type": counts}


def _display_path(path: PathLike) -> str:
    return PurePosixPath(str(Path(path))).as_posix()


def _stable_id(kind: str, path: str, line: int, label: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.:/-]+", "-", label).strip("-") or "item"
    return f"python:{kind}:{path}:{line}:{slug[:96]}"


def _line(node: ast.AST) -> int:
    return int(getattr(node, "lineno", 1) or 1)


def _node_end_line(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 1)) or 1)


def _collapse(value: str) -> str:
    return " ".join(value.strip().split())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract AgentCanvas Python source facts.")
    parser.add_argument("path", help="Python source file to inspect")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    args = parser.parse_args(argv)

    payload = extract_file(args.path)
    indent = None if args.compact else 2
    print(json.dumps(payload, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
