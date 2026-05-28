import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).parent / "leaderboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    points INTEGER NOT NULL,
    datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    length INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_points_desc ON leaderboard(points DESC, id ASC);
CREATE INDEX IF NOT EXISTS idx_user_name ON leaderboard(user_name);
CREATE INDEX IF NOT EXISTS idx_datetime ON leaderboard(datetime);
"""


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def add_entry(user_name: str, points: int, length: int, dt: str | None = None) -> int:
    with _conn() as c:
        if dt is None:
            cur = c.execute(
                "INSERT INTO leaderboard (user_name, points, length) VALUES (?, ?, ?)",
                (user_name, points, length),
            )
        else:
            cur = c.execute(
                "INSERT INTO leaderboard (user_name, points, length, datetime) "
                "VALUES (?, ?, ?, ?)",
                (user_name, points, length, dt),
            )
        return int(cur.lastrowid)


def top_n(n: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, user_name, points, datetime, length "
            "FROM leaderboard ORDER BY points DESC, id ASC LIMIT ?",
            (n,),
        ).fetchall()
    return [dict(r) for r in rows]


def top_10() -> list[dict]:
    return top_n(10)


def user_rank(user_name: str) -> dict | None:
    """Best entry of user + 1-based rank across all entries."""
    with _conn() as c:
        best = c.execute(
            "SELECT id, user_name, points, datetime, length "
            "FROM leaderboard WHERE user_name = ? "
            "ORDER BY points DESC, id ASC LIMIT 1",
            (user_name,),
        ).fetchone()
        if best is None:
            return None
        rank = c.execute(
            "SELECT 1 + COUNT(*) AS r FROM leaderboard "
            "WHERE points > ? OR (points = ? AND id < ?)",
            (best["points"], best["points"], best["id"]),
        ).fetchone()["r"]
    return {**dict(best), "rank": int(rank)}


def total_playtime(user_name: str) -> int:
    """Sum of length (seconds) for user. 0 if no entries."""
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(length), 0) AS total "
            "FROM leaderboard WHERE user_name = ?",
            (user_name,),
        ).fetchone()
    return int(row["total"])


def avg_points_last_7d() -> float:
    """Average points across all entries from last 7 days. 0.0 if none."""
    with _conn() as c:
        row = c.execute(
            "SELECT AVG(points) AS avg_pts FROM leaderboard "
            "WHERE datetime >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')"
        ).fetchone()
    return float(row["avg_pts"]) if row["avg_pts"] is not None else 0.0
