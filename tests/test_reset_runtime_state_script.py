from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_reset_runtime_state_script_moves_runtime_artifacts_into_backup(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    data_dir = repo_root / "data"
    custom_dir = repo_root / "content" / "custom"
    assets_dir = repo_root / "assets"
    assets_variant_dir = repo_root / "assets-dreamshaper"
    backup_dir = repo_root / "backup"
    scripts_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    custom_dir.mkdir(parents=True)
    assets_dir.mkdir(parents=True)
    assets_variant_dir.mkdir(parents=True)
    backup_dir.mkdir(parents=True)

    source_script = Path("scripts/reset-runtime-state.sh")
    target_script = scripts_dir / "reset-runtime-state.sh"
    shutil.copy2(source_script, target_script)
    target_script.chmod(0o755)

    (data_dir / "englishbot.db").write_text("db", encoding="utf-8")
    (repo_root / "test.db").write_text("scratch", encoding="utf-8")
    (assets_dir / "dragon.png").write_text("png", encoding="utf-8")
    (assets_variant_dir / "dragon.png").write_text("png", encoding="utf-8")
    (custom_dir / "fairy-tales.json").write_text("{}", encoding="utf-8")
    (custom_dir / "castle.draft.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [str(target_script), "--backup-name", "manual-reset"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Backup created at:" in result.stdout

    backup_root = repo_root / "backup" / "manual-reset"
    assert (backup_root / "data" / "englishbot.db").exists()
    assert (backup_root / "test.db").exists()
    assert (backup_root / "assets" / "dragon.png").exists()
    assert (backup_root / "assets-dreamshaper" / "dragon.png").exists()
    assert (backup_root / "content" / "custom" / "fairy-tales.json").exists()
    assert (backup_root / "content" / "custom" / "castle.draft.json").exists()

    assert not (data_dir / "englishbot.db").exists()
    assert not (repo_root / "test.db").exists()
    assert not assets_dir.exists()
    assert not assets_variant_dir.exists()
    assert list(custom_dir.iterdir()) == []
    assert data_dir.exists()
    assert custom_dir.exists()
