from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RuntimeVersionInfo:
    package_version: str
    build_number: str | None = None
    git_sha: str | None = None
    git_branch: str | None = None


def get_runtime_version_info(
    environ: Mapping[str, str] | None = None,
) -> RuntimeVersionInfo:
    resolved_environ = environ if environ is not None else os.environ
    return RuntimeVersionInfo(
        package_version=_clean_value(resolved_environ.get("ENGLISHBOT_BUILD_VERSION"))
        or _package_version(),
        build_number=_clean_value(resolved_environ.get("ENGLISHBOT_BUILD_NUMBER")),
        git_sha=_clean_value(resolved_environ.get("ENGLISHBOT_GIT_SHA")),
        git_branch=_clean_value(resolved_environ.get("ENGLISHBOT_GIT_BRANCH")),
    )


def _package_version() -> str:
    try:
        return version("englishbot")
    except PackageNotFoundError:
        return "unknown"


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
