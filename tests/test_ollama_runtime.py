from pathlib import Path

from englishbot.importing.ollama_runtime import resolve_runtime_ollama_model


def test_resolve_runtime_ollama_model_prefers_file_contents(tmp_path: Path) -> None:
    model_path = tmp_path / "ollama_model.txt"
    model_path.write_text("qwen3.5:4b", encoding="utf-8")

    assert (
        resolve_runtime_ollama_model(
            default_model="fallback-model",
            model_file_path=model_path,
        )
        == "qwen3.5:4b"
    )


def test_resolve_runtime_ollama_model_falls_back_when_file_missing(tmp_path: Path) -> None:
    assert (
        resolve_runtime_ollama_model(
            default_model="fallback-model",
            model_file_path=tmp_path / "missing.txt",
        )
        == "fallback-model"
    )
