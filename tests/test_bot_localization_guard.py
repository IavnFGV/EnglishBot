from __future__ import annotations

import ast
from pathlib import Path


def test_tg_calls_with_user_always_include_context_or_language() -> None:
    source_path = Path("src/englishbot/bot.py")
    source_text = source_path.read_text(encoding="utf-8")
    module = ast.parse(source_text)
    violations: list[int] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_tg":
            continue
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        if "user" in keyword_names and "context" not in keyword_names and "language" not in keyword_names:
            violations.append(node.lineno)

    assert not violations, (
        "All _tg(..., user=...) calls must include context=... or language=... "
        f"to prevent mixed-language UI regressions. Lines: {violations}"
    )
