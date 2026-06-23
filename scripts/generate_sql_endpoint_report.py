from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SqlFinding:
    kind: str
    sql: str
    tables: list[str]
    file_path: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class EndpointFinding:
    method: str
    path: str
    file_path: str
    line_start: int
    line_end: int
    sql: list[SqlFinding]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_str_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _stringify(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{...}")
        return "".join(parts)
    return "{...}"


def _extract_tables_from_sql(sql: str) -> list[str]:
    s = re.sub(r"\s+", " ", sql.strip())
    tables: set[str] = set()
    for m in re.finditer(r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", s, flags=re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", s, flags=re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", s, flags=re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"\bINTO\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", s, flags=re.IGNORECASE):
        tables.add(m.group(1))
    for m in re.finditer(r"\bDELETE\s+FROM\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", s, flags=re.IGNORECASE):
        tables.add(m.group(1))
    return sorted(tables)


def _iter_py_files() -> Iterable[Path]:
    targets = [
        ROOT / "app",
        ROOT / "services",
        ROOT / "utils",
        ROOT / "main.py",
    ]
    for t in targets:
        if t.is_file() and t.suffix == ".py":
            yield t
            continue
        if t.is_dir():
            for p in t.rglob("*.py"):
                yield p


def _router_prefix_for_file(file_path: Path) -> str:
    rel = file_path.as_posix().lower()
    if rel.endswith("/app/admin/teams_router.py"):
        return "/api/teams"
    if "/app/" in rel:
        return "/api"
    return ""


def _unwind_chain(call: ast.Call) -> tuple[Optional[str], list[tuple[str, ast.Call]]]:
    steps: list[tuple[str, ast.Call]] = []
    node: ast.AST = call
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        steps.append((node.func.attr, node))
        node = node.func.value
    steps.reverse()
    table_name: Optional[str] = None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in ("table", "from_") and node.args and _is_str_constant(node.args[0]):
            table_name = str(node.args[0].value)
    return table_name, steps


def _tableproxy_sql_from_chain(table: str, steps: list[tuple[str, ast.Call]]) -> tuple[str, list[str]]:
    select_cols = "*"
    order_by: Optional[str] = None
    order_desc = False
    limit: Optional[int] = None
    eq_filters: list[tuple[str, str]] = []
    ilike_filters: list[tuple[str, str]] = []
    neq_filters: list[tuple[str, str]] = []
    in_filters: list[tuple[str, int]] = []
    count_mode = False
    kind = "select"

    for name, c in steps:
        if name == "select":
            if c.args and _is_str_constant(c.args[0]):
                select_cols = str(c.args[0].value)
            for kw in c.keywords or []:
                if kw.arg == "count" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    count_mode = True
        elif name == "eq":
            if len(c.args) >= 2 and _is_str_constant(c.args[0]):
                eq_filters.append((str(c.args[0].value), _stringify(c.args[1])))
        elif name == "ilike":
            if len(c.args) >= 2 and _is_str_constant(c.args[0]):
                ilike_filters.append((str(c.args[0].value), _stringify(c.args[1])))
        elif name == "neq":
            if len(c.args) >= 2 and _is_str_constant(c.args[0]):
                neq_filters.append((str(c.args[0].value), _stringify(c.args[1])))
        elif name == "in_":
            if len(c.args) >= 2 and _is_str_constant(c.args[0]):
                values = c.args[1]
                if isinstance(values, (ast.List, ast.Tuple)):
                    in_filters.append((str(c.args[0].value), len(values.elts)))
                else:
                    in_filters.append((str(c.args[0].value), -1))
        elif name == "order":
            if c.args and _is_str_constant(c.args[0]):
                order_by = str(c.args[0].value)
            for kw in c.keywords or []:
                if kw.arg == "desc" and isinstance(kw.value, ast.Constant):
                    order_desc = bool(kw.value.value)
        elif name == "limit":
            if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, int):
                limit = int(c.args[0].value)
        elif name == "update":
            kind = "update"
        elif name == "insert":
            kind = "insert"
        elif name == "delete":
            kind = "delete"

    if kind == "select":
        sql = f"SELECT {select_cols} FROM {table}"
        conds: list[str] = []
        for col, _ in eq_filters:
            conds.append(f"{col} = %s")
        for col, _ in ilike_filters:
            conds.append(f"{col} ILIKE %s")
        for col, _ in neq_filters:
            conds.append(f"{col} != %s")
        for col, n in in_filters:
            placeholders = "%s, " * max(n, 1)
            placeholders = placeholders.rstrip(", ")
            conds.append(f"{col} IN ({placeholders})")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        if order_by:
            sql += f" ORDER BY {order_by} {'DESC' if order_desc else 'ASC'}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        if count_mode:
            sql += " ; + COUNT(*) query (TableProxy count mode)"
        return sql, [table]

    if kind == "update":
        sql = f"UPDATE {table} SET ... WHERE " + " AND ".join([f"{col} = %s" for col, _ in eq_filters]) if eq_filters else f"UPDATE {table} SET ... WHERE <missing filters>"
        return sql, [table]

    if kind == "insert":
        sql = f"INSERT INTO {table} (...) VALUES (...)"
        return sql, [table]

    if kind == "delete":
        sql = f"DELETE FROM {table} WHERE " + " AND ".join([f"{col} = %s" for col, _ in eq_filters]) if eq_filters else f"DELETE FROM {table} WHERE <missing filters>"
        return sql, [table]

    return f"SELECT {select_cols} FROM {table}", [table]


def _collect_sql(tree: ast.AST, file_path: Path) -> list[SqlFinding]:
    out: list[SqlFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "execute_query":
            if not node.args:
                continue
            sql = _stringify(node.args[0])
            out.append(
                SqlFinding(
                    kind="execute_query",
                    sql=sql.strip(),
                    tables=_extract_tables_from_sql(sql),
                    file_path=str(file_path),
                    line_start=getattr(node, "lineno", 0),
                    line_end=getattr(node, "end_lineno", getattr(node, "lineno", 0)),
                )
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            if not node.args:
                continue
            sql = _stringify(node.args[0])
            out.append(
                SqlFinding(
                    kind="cursor_execute",
                    sql=sql.strip(),
                    tables=_extract_tables_from_sql(sql),
                    file_path=str(file_path),
                    line_start=getattr(node, "lineno", 0),
                    line_end=getattr(node, "end_lineno", getattr(node, "lineno", 0)),
                )
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            table, steps = _unwind_chain(node)
            if table and steps:
                sql, tables = _tableproxy_sql_from_chain(table, steps)
                out.append(
                    SqlFinding(
                        kind="tableproxy",
                        sql=sql,
                        tables=tables,
                        file_path=str(file_path),
                        line_start=getattr(node, "lineno", 0),
                        line_end=getattr(node, "end_lineno", getattr(node, "lineno", 0)),
                    )
                )
    return out


def _extract_endpoints(tree: ast.AST, file_path: Path) -> list[EndpointFinding]:
    endpoints: list[EndpointFinding] = []
    sql_findings = _collect_sql(tree, file_path)
    sql_by_line: list[SqlFinding] = sorted(sql_findings, key=lambda s: (s.line_start, s.line_end))

    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = list(node.decorator_list or [])
        for dec in decorators:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            owner = dec.func.value
            if not isinstance(owner, ast.Name):
                continue
            if owner.id not in ("router", "app"):
                continue
            method = dec.func.attr.upper()
            if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            if not dec.args or not _is_str_constant(dec.args[0]):
                continue
            raw_path = str(dec.args[0].value)
            prefix = ""
            if owner.id == "router":
                prefix = _router_prefix_for_file(file_path)
            full_path = f"{prefix}{raw_path}"

            fn_start = getattr(node, "lineno", 0)
            fn_end = getattr(node, "end_lineno", fn_start)
            related_sql = [s for s in sql_by_line if fn_start <= s.line_start <= fn_end]
            endpoints.append(
                EndpointFinding(
                    method=method,
                    path=full_path,
                    file_path=str(file_path),
                    line_start=fn_start,
                    line_end=fn_end,
                    sql=related_sql,
                )
            )
    return endpoints


def _format_md(endpoints: list[EndpointFinding]) -> str:
    lines: list[str] = []
    lines.append("# SQL Endpoint Report")
    lines.append("")
    lines.append("This report is generated from static code analysis (FastAPI route decorators + SQL call sites).")
    lines.append("TableProxy calls are converted into SQL templates based on services/db_service.py.")
    lines.append("")
    for ep in sorted(endpoints, key=lambda e: (e.path, e.method)):
        rel = os.path.relpath(ep.file_path, str(ROOT)).replace("\\", "/")
        lines.append(f"## {ep.method} {ep.path}")
        lines.append(f"- Handler: {rel}:{ep.line_start}-{ep.line_end}")
        if not ep.sql:
            lines.append("- SQL: (none detected in handler body; may be in called services/repositories)")
            lines.append("")
            continue
        for s in ep.sql:
            srel = os.path.relpath(s.file_path, str(ROOT)).replace("\\", "/")
            tables = ", ".join(s.tables) if s.tables else "(unknown)"
            sql = re.sub(r"\s+", " ", (s.sql or "").strip())
            lines.append(f"- SQL ({s.kind}) {srel}:{s.line_start}-{s.line_end}")
            lines.append(f"  - Tables: {tables}")
            lines.append(f"  - Query: `{sql}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    endpoints: list[EndpointFinding] = []
    for p in _iter_py_files():
        try:
            tree = ast.parse(_read_text(p))
        except Exception:
            continue
        endpoints.extend(_extract_endpoints(tree, p))

    out_path = ROOT / "SQL_ENDPOINT_REPORT.md"
    out_path.write_text(_format_md(endpoints), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()

