import hashlib
import hmac
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PBKDF2_ITERATIONS = 200_000
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32


def _hash_password(password: str) -> str:
    salt = os.urandom(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt,
        PBKDF2_ITERATIONS, dklen=PBKDF2_HASH_BYTES,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected),
    )
    return hmac.compare_digest(dk, expected)

DB_PATH = Path(__file__).parent / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_users_name ON users(user_name);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    points INTEGER NOT NULL,
    datetime TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    length INTEGER NOT NULL,
    won INTEGER NOT NULL DEFAULT 0,
    lives_left INTEGER
);
CREATE INDEX IF NOT EXISTS idx_games_points ON games(points DESC, id ASC);
CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id);
CREATE INDEX IF NOT EXISTS idx_games_datetime ON games(datetime);
"""


class UserExists(Exception):
    pass


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


# --- users -----------------------------------------------------------------

def register(user_name: str, password: str) -> int:
    pw_hash = _hash_password(password)
    with _conn() as c:
        try:
            cur = c.execute(
                "INSERT INTO users (user_name, password) VALUES (?, ?)",
                (user_name, pw_hash),
            )
        except sqlite3.IntegrityError as e:
            raise UserExists(user_name) from e
        return int(cur.lastrowid)


def login(user_name: str, password: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT user_id, user_name, password FROM users WHERE user_name = ?",
            (user_name,),
        ).fetchone()
    if row is None or not _verify_password(password, row["password"]):
        return None
    return {"user_id": row["user_id"], "user_name": row["user_name"]}


def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT user_id, user_name, datetime FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


# --- games / leaderboard ---------------------------------------------------

def add_entry(
    user_id: int,
    points: int,
    length: int,
    won: bool,
    lives_left: int | None = None,
    dt: str | None = None,
) -> int:
    won_int = 1 if won else 0
    with _conn() as c:
        if dt is None:
            cur = c.execute(
                "INSERT INTO games (user_id, points, length, won, lives_left) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, points, length, won_int, lives_left),
            )
        else:
            cur = c.execute(
                "INSERT INTO games (user_id, points, length, won, lives_left, datetime) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, points, length, won_int, lives_left, dt),
            )
        return int(cur.lastrowid)


_GAME_COLS = (
    "g.id, g.user_id, u.user_name, g.points, g.datetime, "
    "g.length, g.won, g.lives_left"
)


def _row_to_game(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["won"] = bool(d["won"])
    return d


def top_n(n: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_GAME_COLS} "
            "FROM games g JOIN users u ON u.user_id = g.user_id "
            "ORDER BY g.points DESC, g.id ASC LIMIT ?",
            (n,),
        ).fetchall()
    return [_row_to_game(r) for r in rows]


def top_10() -> list[dict]:
    return top_n(10)


def user_rank(user_id: int) -> dict | None:
    """Best game of user + 1-based rank across all games."""
    with _conn() as c:
        best = c.execute(
            f"SELECT {_GAME_COLS} "
            "FROM games g JOIN users u ON u.user_id = g.user_id "
            "WHERE g.user_id = ? "
            "ORDER BY g.points DESC, g.id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        if best is None:
            return None
        rank = c.execute(
            "SELECT 1 + COUNT(*) AS r FROM games "
            "WHERE points > ? OR (points = ? AND id < ?)",
            (best["points"], best["points"], best["id"]),
        ).fetchone()["r"]
    return {**_row_to_game(best), "rank": int(rank)}


def count_wins(user_id: int) -> int:
    """Number of games this user has won."""
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM games WHERE user_id = ? AND won = 1",
            (user_id,),
        ).fetchone()
    return int(row["n"])


def total_playtime(user_id: int) -> int:
    """Sum of length (seconds) for user. 0 if no games."""
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(length), 0) AS total FROM games WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row["total"])


def avg_points_last_7d() -> float:
    """Average points across all games from last 7 days. 0.0 if none."""
    with _conn() as c:
        row = c.execute(
            "SELECT AVG(points) AS avg_pts FROM games "
            "WHERE datetime >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-7 days')"
        ).fetchone()
    return float(row["avg_pts"]) if row["avg_pts"] is not None else 0.0
