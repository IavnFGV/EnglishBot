from englishbot import bootstrap
from englishbot import ollama_runtime
from englishbot.application import training_runtime
from englishbot.importing import ollama_runtime as importing_ollama_runtime
from englishbot.importing import runtime as importing_runtime


def test_bootstrap_shim_re_exports_training_runtime() -> None:
    assert bootstrap.build_training_service is training_runtime.build_training_service


def test_bootstrap_shim_re_exports_importing_runtime() -> None:
    assert bootstrap.build_lesson_import_pipeline is importing_runtime.build_lesson_import_pipeline


def test_ollama_runtime_shim_re_exports_importing_runtime_helper() -> None:
    assert ollama_runtime.resolve_runtime_ollama_model is importing_ollama_runtime.resolve_runtime_ollama_model
