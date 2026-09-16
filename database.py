"""
Namesniper - SQLite Database Storage
Stores checked usernames, status (AVAILABLE, CLAIMABLE_IDLE, TAKEN, INVALID), details, and timestamp.
"""
import sqlite3
import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import contextmanager
from config import DATABASE_FILE

class Database:
    def __init__(self, db_path: Path = DATABASE_FILE):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checked_names (
                    nickname TEXT PRIMARY KEY COLLATE NOCASE,
                    status TEXT NOT NULL, -- AVAILABLE, CLAIMABLE_IDLE, TAKEN, INVALID
                    length INTEGER NOT NULL,
                    player_id TEXT,
                    country TEXT,
                    faceit_elo INTEGER,
                    faceit_url TEXT,
                    games_count INTEGER DEFAULT 0,
                    account_created_at TEXT,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            """)
            try:
                conn.execute("ALTER TABLE checked_names ADD COLUMN account_created_at TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON checked_names(status)
            """)
            conn.commit()

    def is_already_checked(self, nickname: str) -> bool:
        """Check if a nickname has already been checked in the past."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM checked_names WHERE nickname = ? COLLATE NOCASE",
                (nickname,)
            )
            return cursor.fetchone() is not None

    def get_already_checked_set(self) -> set:
        """Get set of all checked nicknames in lowercase for fast O(1) set filtering."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT lower(nickname) FROM checked_names")
            return {row[0] for row in cursor.fetchall()}

    def record_result(
        self,
        nickname: str,
        status: str,
        length: int,
        player_id: Optional[str] = None,
        country: Optional[str] = None,
        faceit_elo: Optional[int] = None,
        faceit_url: Optional[str] = None,
        games_count: int = 0,
        account_created_at: Optional[str] = None,
        details: Optional[str] = None
    ) -> None:
        """Insert or replace a checked nickname result."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO checked_names (
                    nickname, status, length, player_id, country, faceit_elo,
                    faceit_url, games_count, account_created_at, checked_at, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(nickname) DO UPDATE SET
                    status=excluded.status,
                    length=excluded.length,
                    player_id=excluded.player_id,
                    country=excluded.country,
                    faceit_elo=excluded.faceit_elo,
                    faceit_url=excluded.faceit_url,
                    games_count=excluded.games_count,
                    account_created_at=excluded.account_created_at,
                    checked_at=excluded.checked_at,
                    details=excluded.details
            """, (
                nickname,
                status,
                length,
                player_id,
                country,
                faceit_elo,
                faceit_url,
                games_count,
                account_created_at,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                details
            ))
            conn.commit()

    def get_results(self, status_filter: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Retrieve recent results filtered by status if provided."""
        with self._connection() as conn:
            if status_filter and status_filter != "ALL":
                cursor = conn.execute("""
                    SELECT * FROM checked_names 
                    WHERE status = ? 
                    ORDER BY checked_at DESC 
                    LIMIT ?
                """, (status_filter, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM checked_names 
                    ORDER BY checked_at DESC 
                    LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Get summary statistics of all checks."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'AVAILABLE' THEN 1 ELSE 0 END) as available,
                    SUM(CASE WHEN status = 'CLAIMABLE_IDLE' THEN 1 ELSE 0 END) as claimable,
                    SUM(CASE WHEN status = 'TAKEN' THEN 1 ELSE 0 END) as taken,
                    SUM(CASE WHEN status = 'INVALID' THEN 1 ELSE 0 END) as invalid
                FROM checked_names
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "total": row["total"] or 0,
                    "available": row["available"] or 0,
                    "claimable": row["claimable"] or 0,
                    "taken": row["taken"] or 0,
                    "invalid": row["invalid"] or 0,
                }
            return {"total": 0, "available": 0, "claimable": 0, "taken": 0, "invalid": 0}

    def clear_database(self) -> None:
        """Clear all records."""
        with self._connection() as conn:
            conn.execute("DELETE FROM checked_names")
            conn.commit()
