import json
import pytest
from pathlib import Path
from utils.storage import StorageManager


def test_storage_save_and_load(tmp_path: Path):
    storage_file = tmp_path / "tournament.json"
    backup_dir = tmp_path / "backups"
    manager = StorageManager(storage_file, backup_dir=backup_dir, max_backups=5)

    test_data = {"name": "UDA Weekly #1", "max_slots": 16}
    manager.save(test_data)

    loaded = manager.load()
    assert loaded == test_data
    assert storage_file.exists()


def test_storage_creates_and_prunes_backups(tmp_path: Path):
    storage_file = tmp_path / "tournament.json"
    backup_dir = tmp_path / "backups"
    manager = StorageManager(storage_file, backup_dir=backup_dir, max_backups=3)

    # First write: no prior file to backup
    manager.save({"version": 1})
    assert len(list(backup_dir.glob("*.json"))) == 0

    # Successive writes create backups
    for v in range(2, 8):
        manager.save({"version": v})

    backups = list(backup_dir.glob("*.json"))
    assert len(backups) <= 3


def test_storage_crash_recovery_from_corrupted_file(tmp_path: Path):
    storage_file = tmp_path / "tournament.json"
    backup_dir = tmp_path / "backups"
    manager = StorageManager(storage_file, backup_dir=backup_dir)

    # Save valid version
    original_data = {"name": "Championship 2026", "participants": ["Player1"]}
    manager.save(original_data)

    # Save a second version so a backup exists
    updated_data = {"name": "Championship 2026", "participants": ["Player1", "Player2"]}
    manager.save(updated_data)

    # Simulate crash / file corruption on primary file
    with open(storage_file, "w", encoding="utf-8") as f:
        f.write("{corrupted_json: [incomplete")

    # Load should detect corruption, recover from the latest valid backup
    recovered = manager.load()
    assert recovered is not None
    assert "Championship 2026" in recovered["name"]


def test_storage_load_missing_file_with_default(tmp_path: Path):
    storage_file = tmp_path / "non_existent.json"
    manager = StorageManager(storage_file)

    loaded = manager.load(default_factory=lambda: {"default": True})
    assert loaded == {"default": True}

