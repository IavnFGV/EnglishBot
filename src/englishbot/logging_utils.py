from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Mapping
from functools import wraps
from time import perf_counter
from typing import Any


def logged_service_call(
    service: str,
    *,
    include: list[str] | tuple[str, ...] | None = None,
    exclude: list[str] | tuple[str, ...] | None = None,
    transforms: Mapping[str, Callable[[Any], Any]] | None = None,
    result: Callable[[Any], Mapping[str, Any]] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    include_set = set(include or [])
    exclude_set = {"self", "cls", *(exclude or [])}
    transforms_map = dict(transforms or {})

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)
        logger = logging.getLogger(func.__module__)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            params = _collect_fields(
                bound.arguments,
                include=include_set,
                exclude=exclude_set,
                transforms=transforms_map,
            )
            start = perf_counter()
            logger.info("%s start%s", service, _format_fields(params))
            try:
                value = func(*args, **kwargs)
            except Exception as error:
                elapsed_ms = int((perf_counter() - start) * 1000)
                logger.exception(
                    "%s error elapsed_ms=%s error=%s%s",
                    service,
                    elapsed_ms,
                    type(error).__name__,
                    _format_fields(params),
                )
                raise

            details = dict(params)
            details["elapsed_ms"] = int((perf_counter() - start) * 1000)
            if result is not None:
                details.update(result(value))
            logger.info("%s done%s", service, _format_fields(details))
            return value

        return wrapper

    return decorator


def _collect_fields(
    arguments: Mapping[str, Any],
    *,
    include: set[str],
    exclude: set[str],
    transforms: Mapping[str, Callable[[Any], Any]],
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name, value in arguments.items():
        if name in exclude:
            continue
        if include and name not in include and name not in transforms:
            continue

        if name in transforms:
            transformed = transforms[name](value)
            if isinstance(transformed, dict):
                fields.update(transformed)
            elif transformed is not None:
                fields[name] = transformed
            continue

        fields[name] = value
    return fields


def _format_fields(fields: Mapping[str, Any]) -> str:
    if not fields:
        return ""
    parts: list[str] = []
    for key, value in fields.items():
        rendered = _render_value(value)
        if rendered == "":
            continue
        parts.append(f"{key}={rendered}")
    if not parts:
        return ""
    return " " + " ".join(parts)


def _render_value(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) > 80:
        text = f"{text[:77]}..."
    if any(ch.isspace() for ch in text):
        return repr(text)
    return text
