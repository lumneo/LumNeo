"""Explicit SQLite transaction boundary for Hardware repository operations."""

from __future__ import annotations

import sqlite3

from lumneo.infrastructure.database.sqlite import SQLiteConnectionFactory

from .sqlite_repository import SQLiteHardwareRepository


class SQLiteHardwareUnitOfWork:
    def __init__(self, connection_factory: SQLiteConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._connection: sqlite3.Connection | None = None
        self.repository: SQLiteHardwareRepository

    async def __aenter__(self) -> "SQLiteHardwareUnitOfWork":
        self._connection = self._connection_factory.connect()
        self._connection.execute("BEGIN")
        self.repository = SQLiteHardwareRepository(self._connection)
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        assert self._connection is not None
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()
            self._connection = None


__all__ = ("SQLiteHardwareUnitOfWork",)
