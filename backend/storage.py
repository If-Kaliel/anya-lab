import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "videos").mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, video_id TEXT NOT NULL, payload TEXT NOT NULL,
                    frontier REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY, experiment_id TEXT NOT NULL,
                    timestamp REAL NOT NULL, payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, hash TEXT NOT NULL,
                    UNIQUE(experiment_id, timestamp));
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY, experiment_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS predictions_no_update BEFORE UPDATE ON predictions
                    BEGIN SELECT RAISE(ABORT, 'Predictions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS predictions_no_delete BEFORE DELETE ON predictions
                    BEGIN SELECT RAISE(ABORT, 'Predictions are append-only'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "anya.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def video(self, video_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM videos WHERE id=?", (video_id,)).fetchone()
        if not row:
            raise ValueError("Gravação não encontrada")
        return json.loads(row[0])

    def experiment(self, experiment_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if not row:
            raise ValueError("Experimento não encontrado")
        return {**json.loads(row["payload"]), "frontier": row["frontier"]}

    def annotations(self, table, video_id):
        if table not in {"observations", "events", "reviews"}:
            raise ValueError("Invalid annotation type")
        with self.connect() as db:
            return [{"id": r[0], **json.loads(r[1])} for r in db.execute(
                f"SELECT id,payload FROM {table} WHERE video_id=? ORDER BY id", (video_id,))]

    def predictions(self, experiment_id):
        with self.connect() as db:
            return [{"id": r["id"], **json.loads(r["payload"]), "hash": r["hash"],
                     "previous_hash": r["previous_hash"]} for r in db.execute(
                "SELECT * FROM predictions WHERE experiment_id=? ORDER BY id", (experiment_id,))]

    def verify(self, experiment_id):
        previous = "0" * 64
        rows = self.predictions(experiment_id)
        for row in rows:
            payload = {k: v for k, v in row.items() if k not in {"id", "hash", "previous_hash"}}
            if row["previous_hash"] != previous or digest({"previous_hash": previous, "payload": payload}) != row["hash"]:
                return {"valid": False, "count": len(rows), "broken_at": row["id"]}
            previous = row["hash"]
        return {"valid": True, "count": len(rows), "head": previous}
