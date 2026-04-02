from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from englishbot.config import Settings
from englishbot.tts_service import (
    PiperTtsSynthesizer,
    TtsHttpService,
    TtsServiceClient,
    TtsTextValidationError,
    build_tts_service,
    create_tts_http_handler,
    validate_tts_text,
)


def test_validate_tts_text_normalizes_and_rejects_cyrillic() -> None:
    assert validate_tts_text("  Magic   lamp  ") == "Magic lamp"

    with pytest.raises(TtsTextValidationError, match="Cyrillic"):
        validate_tts_text("Рrincess")


def test_piper_tts_synthesizer_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    model_path = tmp_path / "voice.onnx"
    config_path = tmp_path / "voice.onnx.json"
    model_path.write_bytes(b"model")
    config_path.write_text("{}", encoding="utf-8")

    def _fake_run(
        cmd: list[str],
        *,
        input: bytes | None = None,
        stdout,
        stderr,
        check: bool,
    ):  # noqa: ANN001
        calls.append(cmd)
        if cmd[0] == "python" and "-m" in cmd and "piper" in cmd:
            output_path = Path(cmd[cmd.index("-f") + 1])
            output_path.write_bytes(b"RIFFfake-wav")
            assert input == b"Princess\n"
        elif cmd[0] == "ffmpeg":
            output_path = Path(cmd[-1])
            output_path.write_bytes(b"OggSfake-ogg")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("englishbot.tts_service.subprocess.run", _fake_run)

    synthesizer = PiperTtsSynthesizer(
        voice_name="en_US-lessac-medium",
        cache_dir=tmp_path / "cache",
        voice_dir=tmp_path / "voices",
        model_path=model_path,
        config_path=config_path,
        python_executable="python",
    )

    first = synthesizer.synthesize(text="Princess")
    second = synthesizer.synthesize(text="Princess")

    assert first == b"OggSfake-ogg"
    assert second == b"OggSfake-ogg"
    assert len(calls) == 2


def test_tts_http_handler_serves_health_and_speak(tmp_path: Path) -> None:
    class _FakeSynthesizer:
        def synthesize(self, *, text: str) -> bytes:
            assert text == "winter"
            return b"OggSfake-ogg"

    service = TtsHttpService(synthesizer=_FakeSynthesizer(), voice_name="en_US-lessac-medium")
    handler = create_tts_http_handler(service)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/healthz") as response:
            assert json.loads(response.read().decode("utf-8")) == {
                "status": "ok",
                "voice_name": "en_US-lessac-medium",
            }

        request = Request(
            f"{base_url}/speak",
            data=json.dumps({"text": "winter"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.headers.get_content_type() == "audio/ogg"
            assert response.read() == b"OggSfake-ogg"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_tts_http_handler_rejects_invalid_text() -> None:
    class _FakeSynthesizer:
        def synthesize(self, *, text: str) -> bytes:
            raise TtsTextValidationError("Text contains Cyrillic characters.")

    service = TtsHttpService(synthesizer=_FakeSynthesizer(), voice_name="en_US-lessac-medium")
    handler = create_tts_http_handler(service)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = Request(
            f"{base_url}/speak",
            data=json.dumps({"text": "Рrincess"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 400
        assert "Cyrillic" in error.value.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_tts_service_client_calls_http_service() -> None:
    class _FakeSynthesizer:
        def synthesize(self, *, text: str) -> bytes:
            return f"audio:{text}".encode("utf-8")

    service = TtsHttpService(synthesizer=_FakeSynthesizer(), voice_name="en_US-lessac-medium")
    handler = create_tts_http_handler(service)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = TtsServiceClient(base_url=f"http://127.0.0.1:{server.server_port}", timeout_sec=5)
        assert client.health()["status"] == "ok"
        assert client.synthesize(text="cloud") == b"audio:cloud"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_build_tts_service_uses_settings_paths(tmp_path: Path) -> None:
    settings = Settings(
        telegram_token="token",
        log_level="INFO",
        tts_voice_name="en_US-lessac-medium",
        tts_cache_dir=tmp_path / "cache",
        tts_voice_dir=tmp_path / "voices",
    )

    service = build_tts_service(settings)

    assert service.health_payload()["voice_name"] == "en_US-lessac-medium"
