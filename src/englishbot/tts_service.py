from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from englishbot.__main__ import configure_logging
from englishbot.config import Settings, create_runtime_config_service

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CYRILLIC_RE = r"[А-Яа-яЁёІіЇїЄєҐґ]"
_ALLOWED_TEXT_RE = rf"^[A-Za-z0-9][A-Za-z0-9 '\-]*$"


class TtsTextValidationError(ValueError):
    pass


class TtsVoiceSelectionError(ValueError):
    pass


def normalize_tts_text(text: str) -> str:
    return " ".join(text.strip().split())


def validate_tts_text(text: str) -> str:
    import re

    normalized = normalize_tts_text(text)
    if not normalized:
        raise TtsTextValidationError("Text is required.")
    if re.search(_CYRILLIC_RE, normalized):
        raise TtsTextValidationError("Text contains Cyrillic characters.")
    if not re.match(_ALLOWED_TEXT_RE, normalized):
        raise TtsTextValidationError("Text contains unsupported characters.")
    return normalized


@dataclass(frozen=True, slots=True)
class PiperVoiceFiles:
    model_path: Path
    config_path: Path


class PiperTtsSynthesizer:
    def __init__(
        self,
        *,
        voice_name: str,
        cache_dir: Path,
        voice_dir: Path,
        model_path: Path | None = None,
        config_path: Path | None = None,
        python_executable: str = sys.executable,
    ) -> None:
        self._voice_name = voice_name
        self._cache_dir = cache_dir
        self._voice_dir = voice_dir
        self._model_path = model_path
        self._config_path = config_path
        self._python_executable = python_executable

    def synthesize(self, *, text: str) -> bytes:
        normalized = validate_tts_text(text)
        cache_path = self._cache_path(normalized)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path.read_bytes()
        voice_files = self._resolve_voice_files()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(suffix=".wav", dir=cache_path.parent, delete=False) as tmp_wav_file:
            temp_wav_path = Path(tmp_wav_file.name)
        with NamedTemporaryFile(suffix=".ogg", dir=cache_path.parent, delete=False) as tmp_ogg_file:
            temp_ogg_path = Path(tmp_ogg_file.name)
        try:
            piper_result = subprocess.run(
                [
                    self._python_executable,
                    "-m",
                    "piper",
                    "-m",
                    str(voice_files.model_path),
                    "-c",
                    str(voice_files.config_path),
                    "-f",
                    str(temp_wav_path),
                ],
                input=(normalized + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if piper_result.returncode != 0 or not temp_wav_path.exists() or temp_wav_path.stat().st_size == 0:
                stderr = piper_result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Piper synthesis failed: {stderr or 'unknown error'}")
            ffmpeg_result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(temp_wav_path),
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "48k",
                    str(temp_ogg_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if ffmpeg_result.returncode != 0 or not temp_ogg_path.exists() or temp_ogg_path.stat().st_size == 0:
                stderr = ffmpeg_result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"ffmpeg conversion failed: {stderr or 'unknown error'}")
            temp_ogg_path.replace(cache_path)
        finally:
            if temp_wav_path.exists():
                temp_wav_path.unlink()
            if temp_ogg_path.exists():
                temp_ogg_path.unlink()
        return cache_path.read_bytes()

    def _resolve_voice_files(self) -> PiperVoiceFiles:
        model_path = self._model_path
        config_path = self._config_path
        if model_path is not None and config_path is not None:
            return PiperVoiceFiles(model_path=model_path, config_path=config_path)
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        model_path = self._voice_dir / f"{self._voice_name}.onnx"
        config_path = self._voice_dir / f"{self._voice_name}.onnx.json"
        if model_path.exists() and config_path.exists():
            return PiperVoiceFiles(model_path=model_path, config_path=config_path)
        logger.info("Downloading Piper voice %s into %s", self._voice_name, self._voice_dir)
        from piper.download_voices import download_voice

        download_voice(self._voice_name, self._voice_dir)
        return PiperVoiceFiles(model_path=model_path, config_path=config_path)

    def _cache_path(self, text: str) -> Path:
        digest = hashlib.sha256(f"{self._voice_name}:{text}".encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.ogg"


class TtsHttpService:
    def __init__(
        self,
        *,
        default_voice_name: str,
        voice_variants: tuple[str, ...],
        cache_dir: Path,
        voice_dir: Path,
        model_path: Path | None = None,
        config_path: Path | None = None,
        python_executable: str = sys.executable,
    ) -> None:
        self._default_voice_name = default_voice_name
        self._voice_variants = _normalize_voice_variants(default_voice_name, voice_variants)
        self._cache_dir = cache_dir
        self._voice_dir = voice_dir
        self._default_model_path = model_path
        self._default_config_path = config_path
        self._python_executable = python_executable
        self._synthesizers: dict[str, PiperTtsSynthesizer] = {}

    def health_payload(self) -> dict[str, object]:
        return {
            "status": "ok",
            "voice_name": self._default_voice_name,
            "voice_variants": list(self._voice_variants),
        }

    def synthesize(self, *, text: str, voice_name: str | None = None) -> bytes:
        selected_voice_name = self._resolve_voice_name(voice_name)
        synthesizer = self._get_synthesizer(selected_voice_name)
        return synthesizer.synthesize(text=text)

    def _resolve_voice_name(self, voice_name: str | None) -> str:
        selected_voice_name = (voice_name or self._default_voice_name).strip()
        if selected_voice_name not in self._voice_variants:
            raise TtsVoiceSelectionError(f"Voice '{selected_voice_name}' is not configured.")
        return selected_voice_name

    def _get_synthesizer(self, voice_name: str) -> PiperTtsSynthesizer:
        synthesizer = self._synthesizers.get(voice_name)
        if synthesizer is not None:
            return synthesizer
        model_path = self._default_model_path if voice_name == self._default_voice_name else None
        config_path = self._default_config_path if voice_name == self._default_voice_name else None
        created = PiperTtsSynthesizer(
            voice_name=voice_name,
            cache_dir=self._cache_dir,
            voice_dir=self._voice_dir,
            model_path=model_path,
            config_path=config_path,
            python_executable=self._python_executable,
        )
        self._synthesizers[voice_name] = created
        return created


def _normalize_voice_variants(default_voice_name: str, voice_variants: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    for candidate in (default_voice_name, *voice_variants):
        normalized = candidate.strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return tuple(ordered)


def create_tts_http_handler(service: TtsHttpService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/healthz":
                self._write_json(HTTPStatus.NOT_FOUND, {"message": "Not found."})
                return
            self._write_json(HTTPStatus.OK, service.health_payload())

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/speak":
                self._write_json(HTTPStatus.NOT_FOUND, {"message": "Not found."})
                return
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._write_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid JSON body."})
                return
            text = str(payload.get("text", ""))
            voice_name = payload.get("voice_name")
            if voice_name is not None:
                voice_name = str(voice_name)
            try:
                audio_bytes = service.synthesize(text=text, voice_name=voice_name)
            except (TtsTextValidationError, TtsVoiceSelectionError) as error:
                self._write_json(HTTPStatus.BAD_REQUEST, {"message": str(error)})
                return
            except Exception:
                logger.exception("TTS synthesis failed")
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": "TTS synthesis failed."})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/ogg")
            self.send_header("Content-Length", str(len(audio_bytes)))
            self.end_headers()
            self.wfile.write(audio_bytes)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            logger.debug("TTS HTTP %s", format % args)

        def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


class TtsServiceClient:
    def __init__(self, *, base_url: str, timeout_sec: int = 15) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_sec = timeout_sec

    def health(self) -> dict[str, object]:
        with urlopen(urljoin(self._base_url, "healthz"), timeout=self._timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))

    def synthesize(self, *, text: str, voice_name: str | None = None) -> bytes:
        payload: dict[str, object] = {"text": text}
        if voice_name is not None:
            payload["voice_name"] = voice_name
        request = Request(
            urljoin(self._base_url, "speak"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_sec) as response:
                return response.read()
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"TTS HTTP error {error.code}: {body}") from error


def build_tts_service(settings: Settings) -> TtsHttpService:
    tts = settings.tts
    return TtsHttpService(
        default_voice_name=tts.voice_name,
        voice_variants=tts.voice_variants,
        cache_dir=tts.cache_dir,
        voice_dir=tts.voice_dir,
        model_path=tts.voice_model_path,
        config_path=tts.voice_config_path,
        python_executable=sys.executable,
    )


def log_tts_service_settings(settings: Settings) -> None:
    tts = settings.tts
    logger.info(
        "TTS service settings host=%s port=%s voice_name=%s voice_variants=%s "
        "cache_dir=%s voice_dir=%s voice_model_path=%s voice_config_path=%s",
        tts.host,
        tts.port,
        tts.voice_name,
        tts.voice_variants,
        tts.cache_dir,
        tts.voice_dir,
        tts.voice_model_path,
        tts.voice_config_path,
    )


def main() -> None:
    env_file_path = _REPO_ROOT / ".env"
    load_dotenv(env_file_path, override=True)
    config_service = create_runtime_config_service(env_file_path=env_file_path)
    settings = Settings.from_config_service(config_service)
    configure_logging(
        settings.log_level,
        log_file_path=settings.log_file_path,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )
    log_tts_service_settings(settings)
    service = build_tts_service(settings)
    handler = create_tts_http_handler(service)
    tts = settings.tts
    server = ThreadingHTTPServer((tts.host, tts.port), handler)
    logger.info(
        "Starting TTS service host=%s port=%s voice_name=%s cache_dir=%s voice_dir=%s",
        tts.host,
        tts.port,
        tts.voice_name,
        tts.cache_dir,
        tts.voice_dir,
    )
    with server:
        server.serve_forever()


if __name__ == "__main__":
    main()
