"""
Atomic JSON storage manager with automatic backup archiving and crash recovery.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Handles atomic file writes, crash recovery, and automated backup rotation for JSON data.
    """

    def __init__(
        self,
        file_path: Path,
        backup_dir: Path | None = None,
        max_backups: int = 20,
    ):
        self.file_path = Path(file_path).resolve()
        self.backup_dir = (
            Path(backup_dir).resolve()
            if backup_dir
            else self.file_path.parent / "backups"
        )
        self.max_backups = max_backups
        self._lock = threading.Lock()

        # Ensure directories exist
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def load(self, default_factory: Any = None) -> dict[str, Any]:
        """
        Loads data from the primary file. If corrupted or missing, attempts recovery
        from the most recent valid backup. If no valid backup exists, returns default_factory().
        """
        with self._lock:
            if not self.file_path.exists():
                logger.info("Storage file %s not found. Checking backups...", self.file_path)
                recovered = self._recover_from_backup()
                if recovered is not None:
                    return recovered
                logger.info("No backups found. Initializing with default data.")
                return default_factory() if callable(default_factory) else (default_factory or {})

            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        raise ValueError("Storage file is empty")
                    return json.loads(content)
            except (json.JSONDecodeError, ValueError, OSError) as e:
                logger.warning("Corrupted primary storage file %s: %s. Attempting recovery...", self.file_path, e)
                recovered = self._recover_from_backup()
                if recovered is not None:
                    return recovered
                logger.error("Recovery failed. Using default data.")
                return default_factory() if callable(default_factory) else (default_factory or {})

    def save(self, data: dict[str, Any], create_backup: bool = True) -> None:
        """
        Atomically writes data to the primary storage file. Creates a rotating backup
        of the prior valid version if requested.
        """
        with self._lock:
            # Create backup of current file if it exists and has content
            if create_backup and self.file_path.exists() and self.file_path.stat().st_size > 0:
                self._archive_backup()

            # Atomic write via temporary file in the same directory
            dir_path = self.file_path.parent
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    dir=dir_path,
                    delete=False,
                    encoding="utf-8",
                    suffix=".tmp",
                ) as tf:
                    temp_file = Path(tf.name)
                    json.dump(data, tf, indent=2, ensure_ascii=False)
                    tf.flush()
                    os.fsync(tf.fileno())

                # Atomic replace
                os.replace(temp_file, self.file_path)
            except Exception as e:
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except OSError:
                        pass
                logger.error("Failed to write storage file atomically: %s", e)
                raise

    def _archive_backup(self) -> None:
        """
        Creates a timestamped snapshot of the current primary storage file and rotates old backups.
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            backup_file = self.backup_dir / f"{self.file_path.stem}_{timestamp}.json"
            shutil.copy2(self.file_path, backup_file)
            self._prune_backups()
        except Exception as e:
            logger.warning("Failed to archive backup: %s", e)

    def _prune_backups(self) -> None:
        """
        Removes oldest backups exceeding max_backups.
        """
        try:
            backups = sorted(
                self.backup_dir.glob(f"{self.file_path.stem}_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old_backup in backups[self.max_backups:]:
                try:
                    old_backup.unlink()
                except OSError:
                    pass
        except Exception as e:
            logger.warning("Failed to prune backups: %s", e)

    def _recover_from_backup(self) -> dict[str, Any] | None:
        """
        Scans backups from newest to oldest and restores the first readable JSON.
        """
        backups = sorted(
            self.backup_dir.glob(f"{self.file_path.stem}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for backup in backups:
            try:
                with open(backup, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        continue
                    data = json.loads(content)
                    logger.info("Successfully recovered from backup: %s", backup.name)
                    shutil.copy2(backup, self.file_path)
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Backup %s is unreadable: %s", backup.name, e)
                continue

        return None

