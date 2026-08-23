"""SQLite connection creation and migration ownership."""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path


class SQLiteConnectionFactory:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        migration = (
            files("lumneo.persistence.migrations")
            .joinpath("0001_hardware.sql")
            .read_text(encoding="utf-8")
        )
        connection = self.connect()
        try:
            connection.executescript(migration)
            connection.commit()
        finally:
            connection.close()


__all__ = ("SQLiteConnectionFactory",)
