from __future__ import annotations

from pathlib import Path

from englishbot.application.fill_word_audio_use_cases import FillWordAudioUseCase
from englishbot.infrastructure.sqlite_store import SQLiteContentStore


class FakeTtsClient:
    def __init__(self, bytes_by_word: dict[str, bytes]) -> None:
        self.bytes_by_word = bytes_by_word
        self.calls: list[str] = []

    def synthesize(self, *, text: str) -> bytes:
        self.calls.append(text)
        return self.bytes_by_word[text]


def _build_store(tmp_path: Path) -> SQLiteContentStore:
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
                },
                {
                    "id": "bad",
                    "english_word": "bad",
                    "translation": "плохой",
                },
            ],
        }
    )
    return store


def test_fill_word_audio_use_case_generates_audio_assets_and_updates_store(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    client = FakeTtsClient({"good": b"wav-good", "bad": b"wav-bad"})
    use_case = FillWordAudioUseCase(
        store=store,
        tts_client=client,
        assets_dir=tmp_path / "assets",
    )

    summary = use_case.execute()

    assert summary.scanned_count == 2
    assert summary.updated_count == 2
    assert summary.skipped_count == 0
    assert summary.failed_count == 0
    assert client.calls == ["bad", "good"]

    good = store.get_vocabulary_item("good")
    bad = store.get_vocabulary_item("bad")
    assert good is not None
    assert bad is not None
    assert good.audio_ref == (tmp_path / "assets" / "basics" / "audio" / "good.ogg").as_posix()
    assert bad.audio_ref == (tmp_path / "assets" / "basics" / "audio" / "bad.ogg").as_posix()
    assert (tmp_path / "assets" / "basics" / "audio" / "good.ogg").read_bytes() == b"wav-good"
    assert (tmp_path / "assets" / "basics" / "audio" / "bad.ogg").read_bytes() == b"wav-bad"


def test_fill_word_audio_use_case_skips_existing_local_audio_without_force(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    existing_path = tmp_path / "assets" / "basics" / "audio" / "good.ogg"
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_bytes(b"already-there")
    store.update_word_audio(item_id="good", audio_ref=existing_path.as_posix())
    client = FakeTtsClient({"bad": b"wav-bad"})
    use_case = FillWordAudioUseCase(
        store=store,
        tts_client=client,
        assets_dir=tmp_path / "assets",
    )

    summary = use_case.execute()

    assert summary.scanned_count == 2
    assert summary.updated_count == 1
    assert summary.skipped_count == 1
    assert summary.failed_count == 0
    assert client.calls == ["bad"]


def test_fill_word_audio_use_case_dry_run_does_not_write_or_update(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    client = FakeTtsClient({"bad": b"wav-bad", "good": b"wav-good"})
    use_case = FillWordAudioUseCase(
        store=store,
        tts_client=client,
        assets_dir=tmp_path / "assets",
    )

    summary = use_case.execute(limit=1, dry_run=True)

    assert summary.scanned_count == 1
    assert summary.updated_count == 1
    assert summary.skipped_count == 0
    assert summary.failed_count == 0
    assert store.get_vocabulary_item("bad").audio_ref is None
    assert not (tmp_path / "assets" / "basics" / "audio" / "bad.ogg").exists()
