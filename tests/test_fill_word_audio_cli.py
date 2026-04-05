from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from englishbot.fill_word_audio import app
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakeTtsServiceClient:
    def __init__(self, **_: object) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def synthesize(self, *, text: str, voice_name: str | None = None) -> bytes:
        self.calls.append((text, voice_name))
        return f"wav:{text}".encode("utf-8")


def test_fill_word_audio_cli_updates_missing_audio(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"CONTENT_DB_PATH={(tmp_path / 'data' / 'englishbot.db').as_posix()}",
                "TTS_SERVICE_BASE_URL=http://127.0.0.1:8090",
                "TTS_SERVICE_TIMEOUT_SEC=15",
                "TTS_VOICE_NAME=en_US-libritts-high",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    store = SQLiteContentStore(db_path=tmp_path / "data" / "englishbot.db")
    store.initialize()
    store.upsert_content_pack(
        {
            "topic": {"id": "basics", "title": "Basics"},
            "lessons": [],
            "vocabulary_items": [
                {
                    "id": "good",
                    "english_word": "good",
                    "translation": "хороший",
                }
            ],
        }
    )
    monkeypatch.setattr("englishbot.fill_word_audio._REPO_ROOT", tmp_path)
    monkeypatch.setattr("englishbot.fill_word_audio.TtsServiceClient", FakeTtsServiceClient)

    result = CliRunner().invoke(
        app,
        [
            "--assets-dir",
            str(tmp_path / "assets"),
            "--log-level",
            "DEBUG",
        ],
    )

    assert result.exit_code == 0
    saved = store.get_vocabulary_item("good")
    assert saved is not None
    assert saved.audio_ref == (tmp_path / "assets" / "basics" / "audio" / "good.ogg").as_posix()
    assert (tmp_path / "assets" / "basics" / "audio" / "good.ogg").read_bytes() == b"wav:good"
