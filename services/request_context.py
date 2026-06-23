from __future__ import annotations

import contextvars
from typing import Any, Dict, Optional

_ctx: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("mm_request_ctx", default={})


def init_request_context() -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "token": None,
        "user": None,
        "timings_ms": {"auth": 0.0, "rbac": 0.0, "sql": 0.0, "total": 0.0},
        "sql_calls": 0,
        "cache": {
            "is_global_superadmin": None,
            "user_roles": {},
            "role_permissions": {},
            "permission_checks": {},
        },
    }
    _ctx.set(ctx)
    return ctx


def get_request_context() -> Dict[str, Any]:
    return _ctx.get()


def set_request_token(token: Optional[str]) -> None:
    ctx = get_request_context()
    if ctx:
        ctx["token"] = token


def set_request_user(user: Optional[Dict[str, Any]]) -> None:
    ctx = get_request_context()
    if ctx:
        ctx["user"] = user


def add_timing_ms(key: str, delta_ms: float) -> None:
    ctx = get_request_context()
    timings = (ctx or {}).get("timings_ms")
    if isinstance(timings, dict) and key in timings:
        timings[key] = float(timings.get(key, 0.0)) + float(delta_ms)


def add_sql_call(delta_ms: float) -> None:
    ctx = get_request_context()
    if ctx:
        ctx["sql_calls"] = int(ctx.get("sql_calls", 0)) + 1
    add_timing_ms("sql", delta_ms)

