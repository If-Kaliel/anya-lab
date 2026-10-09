import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


ANNOTATION_TABLES = {"observations", "events", "reviews"}


class AnnotationConflict(ValueError):
    pass


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
                CREATE TABLE IF NOT EXISTS annotation_revisions (
                    id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, kind TEXT NOT NULL,
                    annotation_id INTEGER NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL,
                    UNIQUE(kind, annotation_id, revision));
                CREATE INDEX IF NOT EXISTS annotation_revision_video
                    ON annotation_revisions(video_id, kind, annotation_id, revision);
                CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON annotation_revisions
                    BEGIN SELECT RAISE(ABORT, 'Annotation revisions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON annotation_revisions
                    BEGIN SELECT RAISE(ABORT, 'Annotation revisions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS predictions_no_update BEFORE UPDATE ON predictions
                    BEGIN SELECT RAISE(ABORT, 'Predictions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS predictions_no_delete BEFORE DELETE ON predictions
                    BEGIN SELECT RAISE(ABORT, 'Predictions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_update BEFORE UPDATE ON evaluations
                    BEGIN SELECT RAISE(ABORT, 'Evaluation reports are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_delete BEFORE DELETE ON evaluations
                    BEGIN SELECT RAISE(ABORT, 'Evaluation reports are append-only'); END;
            """)
            for table in ANNOTATION_TABLES:
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                        BEFORE {action} ON {table} BEGIN
                        SELECT RAISE(ABORT, 'Original annotations are append-only'); END""")

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
        histories = self.annotation_histories(video_id, table)
        if any(not h["valid"] for h in histories):
            raise ValueError("Falha de integridade no histórico de anotações")
        return [{"id": h["id"], "revision": h["current_revision"], **h["entries"][-1]["annotation"]}
                for h in histories if not h["retracted"]]

    def annotation_snapshot(self, video_id):
        histories = self.annotation_histories(video_id)
        if any(not h["valid"] for h in histories):
            raise ValueError("Falha de integridade no histórico de anotações")
        return {kind: [{"id": h["id"], "revision": h["current_revision"], **h["entries"][-1]["annotation"]}
                       for h in histories if h["kind"] == kind and not h["retracted"]]
                for kind in sorted(ANNOTATION_TABLES)}

    @staticmethod
    def _history(table, video_id, annotation_id, original, revisions):
        payload = {"kind": table, "video_id": video_id, "annotation_id": annotation_id,
                   "revision": 0, "annotation": original, "retracted": False,
                   "reason": "Registro original", "recorded_at": original.get("recorded_at")}
        previous = "0" * 64
        head = digest({"previous_hash": previous, "payload": payload})
        entries = [{**payload, "hash": head, "previous_hash": previous}]
        valid = True
        for row in revisions:
            try:
                payload = json.loads(row["payload"])
                if not isinstance(payload, dict) or not set(entries[0]).difference({"hash", "previous_hash"}).issubset(payload):
                    valid = False
                    break
            except json.JSONDecodeError:
                valid = False
                break
            valid = valid and row["previous_hash"] == head and payload["revision"] == len(entries)
            valid = valid and row["revision"] == payload["revision"]
            valid = valid and digest({"previous_hash": head, "payload": payload}) == row["hash"]
            valid = valid and payload["kind"] == table and payload["annotation_id"] == annotation_id and payload["video_id"] == video_id
            entries.append({**payload, "hash": row["hash"], "previous_hash": row["previous_hash"]})
            head = row["hash"]
        return {"kind": table, "id": annotation_id, "current_revision": entries[-1]["revision"],
                "retracted": entries[-1]["retracted"], "valid": bool(valid), "entries": entries}

    def annotation_histories(self, video_id, table=None):
        if table is not None and table not in ANNOTATION_TABLES:
            raise ValueError("Invalid annotation type")
        result = []
        with self.connect() as db:
            db.execute("BEGIN")
            revisions = {}
            for row in db.execute("SELECT * FROM annotation_revisions WHERE video_id=? ORDER BY revision", (video_id,)):
                revisions.setdefault((row["kind"], row["annotation_id"]), []).append(row)
            for kind in sorted([table] if table else ANNOTATION_TABLES):
                for row in db.execute(f"SELECT id,payload FROM {kind} WHERE video_id=? ORDER BY id", (video_id,)):
                    result.append(self._history(kind, video_id, row["id"], json.loads(row["payload"]),
                                                revisions.get((kind, row["id"]), [])))
        return result

    def revise_annotation(self, table, video_id, annotation_id, expected_revision, reason,
                          annotation=None, retract=False, target_revision=None):
        if table not in ANNOTATION_TABLES:
            raise ValueError("Invalid annotation type")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            original = db.execute(f"SELECT payload FROM {table} WHERE id=? AND video_id=?",
                                  (annotation_id, video_id)).fetchone()
            if not original:
                raise ValueError("Anotação não encontrada nesta gravação")
            rows = db.execute("SELECT * FROM annotation_revisions WHERE kind=? AND annotation_id=? ORDER BY revision",
                              (table, annotation_id)).fetchall()
            history = self._history(table, video_id, annotation_id, json.loads(original[0]), rows)
            if not history["valid"]:
                raise ValueError("Falha de integridade no histórico de anotações")
            if history["current_revision"] != expected_revision:
                raise AnnotationConflict("A anotação mudou em outra operação. Atualize o histórico antes de corrigir.")
            latest = history["entries"][-1]
            if target_revision is not None:
                if target_revision >= len(history["entries"]) or history["entries"][target_revision]["retracted"]:
                    raise ValueError("Versão anterior inexistente ou retirada")
                annotation = history["entries"][target_revision]["annotation"]
            elif history["retracted"]:
                raise ValueError("Restaure uma versão anterior antes de editar a anotação retirada")
            if retract:
                annotation = latest["annotation"]
            if annotation is None:
                raise ValueError("Dados da anotação ausentes")
            payload = {"kind": table, "video_id": video_id, "annotation_id": annotation_id,
                       "revision": expected_revision + 1, "annotation": annotation, "retracted": retract,
                       "reason": reason, "recorded_at": datetime.now(timezone.utc).isoformat()}
            previous_hash = latest["hash"]
            head = digest({"previous_hash": previous_hash, "payload": payload})
            db.execute("INSERT INTO annotation_revisions(video_id,kind,annotation_id,revision,payload,previous_hash,hash) VALUES(?,?,?,?,?,?,?)",
                       (video_id, table, annotation_id, payload["revision"], canonical(payload), previous_hash, head))
            return {**payload, "hash": head, "previous_hash": previous_hash}

    def predictions(self, experiment_id):
        with self.connect() as db:
            return [{"id": r["id"], **json.loads(r["payload"]), "hash": r["hash"],
                     "previous_hash": r["previous_hash"]} for r in db.execute(
                "SELECT * FROM predictions WHERE experiment_id=? ORDER BY id", (experiment_id,))]

    def verify(self, experiment_id):
        return self.verify_predictions(self.predictions(experiment_id))

    @staticmethod
    def verify_predictions(rows):
        previous = "0" * 64
        for row in rows:
            payload = {k: v for k, v in row.items() if k not in {"id", "hash", "previous_hash"}}
            if row["previous_hash"] != previous or digest({"previous_hash": previous, "payload": payload}) != row["hash"]:
                return {"valid": False, "count": len(rows), "broken_at": row["id"]}
            previous = row["hash"]
        return {"valid": True, "count": len(rows), "head": previous}
