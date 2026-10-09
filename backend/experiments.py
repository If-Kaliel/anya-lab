import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from backend.contracts import CLASSES, ExperimentInput
from backend.evaluation import metrics, resolve
from backend.models import Heuristic, Historical
from backend.storage import Store, canonical, digest
from backend.temporal import snapshot
from backend.video import frame_at, perceive


def now():
    return datetime.now(timezone.utc).isoformat()


class ExperimentEngine:
    def __init__(self, store: Store, frames=None):
        self.store = store
        self.frames = frames

    def create(self, config: ExperimentInput):
        video = self.store.video(config.video_id)
        if config.start + config.horizon > video["duration"]:
            raise ValueError("O início deve deixar 15 segundos completos para avaliação")
        counts = dict.fromkeys(CLASSES, 0)
        training_hashes = []
        if config.model_id == "historical-v1":
            if not config.training_match_ids:
                raise ValueError("Selecione partidas de treinamento com intervalos revisados")
            for match in sorted(set(config.training_match_ids)):
                training_video = self.store.video(match)
                if match == config.video_id or training_video["split"] != "train":
                    raise ValueError("Vazamento: baseline histórico aceita apenas outras partidas do split train")
                training_annotations = self.store.annotation_snapshot(match)
                events, reviews = training_annotations["events"], training_annotations["reviews"]
                training_hashes.append({"match_id": match, "annotation_hash": digest({"events": events, "reviews": reviews})})
                t = 0.0
                while t + 15 <= training_video["duration"]:
                    label, _ = resolve(events, reviews, t)
                    if label is not None:
                        counts[label] += 1
                    t += 5
            if not sum(counts.values()):
                raise ValueError("Nenhuma janela de treinamento revisada e confiável")
        elif config.training_match_ids:
            raise ValueError("O modelo heurístico não utiliza partidas de treinamento")
        observations = self.store.annotations("observations", config.video_id)
        experiment = {
            "id": uuid4().hex, "schema_version": "1.0", "config": config.model_dump(),
            "created_at": now(), "model_version": "1.0.0", "training_counts": counts,
            "training_provenance": training_hashes, "observation_snapshot": observations,
            "observation_snapshot_hash": digest(observations),
            "mode": "technical_demo" if video["synthetic"] else "unvalidated_baseline",
            "video_sha256": video["sha256"],
        }
        with self.store.connect() as db:
            db.execute("INSERT INTO experiments VALUES(?,?,?,?)", (
                experiment["id"], config.video_id, canonical(experiment), -1))
        return {**experiment, "frontier": -1}

    def step(self, experiment_id, timestamp):
        exp = self.store.experiment(experiment_id)
        config = exp["config"]
        video = self.store.video(config["video_id"])
        previous = self.store.predictions(experiment_id)
        expected = config["start"] + len(previous) * config["step"]
        if abs(expected - timestamp) > 1e-6:
            raise ValueError(f"Próximo instante autorizado: {expected:.3f}s")
        if timestamp + config["horizon"] > video["duration"]:
            raise ValueError("Experimento concluído: não há horizonte completo restante")
        started = time.perf_counter()
        extract = self.frames.frame_at if self.frames else frame_at
        actual_time, png = extract(self.store.root / "videos" / video["stored_name"], video["frame_timestamps"], timestamp)
        pixels = list(perceive(png, actual_time))
        # Retain prior measured observations, with no labels or storage capability.
        prior_pixels = [o for o in previous[-1]["observations"] if o["source"] != "manual"] if previous else []
        context = snapshot(exp["observation_snapshot"] + prior_pixels + pixels, timestamp)
        model = Heuristic() if config["model_id"] == "heuristic-v1" else Historical(exp["training_counts"])
        probabilities, evidence = model.predict(context)
        observations = [asdict(o) for o in context.observations]
        unknown_rate = sum(o.confidence == 0 for o in context.observations) / max(1, len(observations))
        payload = {
            "experiment_id": experiment_id, "match_id": config["video_id"],
            "model_id": config["model_id"], "model_version": exp["model_version"],
            "timestamp": timestamp, "frame_timestamp": actual_time, "horizon": config["horizon"],
            "perception_version": "pixels-1.1.0",
            "probabilities": probabilities.model_dump(), "observations": observations,
            "unknown_rate": unknown_rate, "evidence": evidence,
            "explanation": "Baseline não validado. " + " · ".join(evidence),
            "config_hash": digest(config), "config": config,
            "latency_ms": (time.perf_counter() - started) * 1000, "generated_at": now(),
            "mode": exp["mode"],
        }
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Serialize writers and recheck the frontier after acquiring the lock.
            count = db.execute("SELECT COUNT(*) FROM predictions WHERE experiment_id=?", (experiment_id,)).fetchone()[0]
            if abs(config["start"] + count * config["step"] - timestamp) > 1e-6:
                raise ValueError("Outro processo já registrou essa previsão")
            head = db.execute("SELECT hash FROM predictions WHERE experiment_id=? ORDER BY id DESC LIMIT 1", (experiment_id,)).fetchone()
            previous_hash = head[0] if head else "0" * 64
            row_hash = digest({"previous_hash": previous_hash, "payload": payload})
            db.execute("INSERT INTO predictions(experiment_id,timestamp,payload,previous_hash,hash) VALUES(?,?,?,?,?)", (
                experiment_id, timestamp, canonical(payload), previous_hash, row_hash))
            db.execute("UPDATE experiments SET frontier=? WHERE id=?", (timestamp, experiment_id))
        return self.store.predictions(experiment_id)[-1]

    def reveal(self, experiment_id):
        exp = self.store.experiment(experiment_id)
        predictions = self.store.predictions(experiment_id)
        integrity = self.store.verify_predictions(predictions)
        if not integrity["valid"]:
            raise ValueError("Falha de integridade; avaliação recusada")
        video_id = exp["config"]["video_id"]
        evaluation_annotations = self.store.annotation_snapshot(video_id)
        events, reviews = evaluation_annotations["events"], evaluation_annotations["reviews"]
        rows = []
        for prediction in predictions:
            label, reason = resolve(events, reviews, prediction["timestamp"], prediction["horizon"])
            rows.append({**prediction, "label": label, "reason": reason})
        report = {"schema_version": "1.0", "experiment_id": experiment_id,
                  "revealed_at": now(), "annotation_hash": digest({"events": events, "reviews": reviews}),
                  "prediction_chain_head": integrity["head"], "metrics": metrics(rows),
                  "rows": rows, "config": exp["config"], "mode": exp["mode"]}
        with self.store.connect() as db:
            db.execute("INSERT INTO evaluations(experiment_id,payload) VALUES(?,?)", (experiment_id, canonical(report)))
        return report

    def report(self, experiment_id):
        self.store.experiment(experiment_id)
        with self.store.connect() as db:
            row = db.execute("SELECT payload FROM evaluations WHERE experiment_id=? ORDER BY id DESC LIMIT 1", (experiment_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def reports(self, experiment_id):
        self.store.experiment(experiment_id)
        with self.store.connect() as db:
            return [{"id": row[0], "report": json.loads(row[1])} for row in db.execute(
                "SELECT id,payload FROM evaluations WHERE experiment_id=? ORDER BY id DESC", (experiment_id,))]

    def report_status(self, experiment_id):
        exp = self.store.experiment(experiment_id)
        report = self.report(experiment_id)
        if not report:
            return {"has_report": False, "stale": False}
        video_id = exp["config"]["video_id"]
        current = self.store.annotation_snapshot(video_id)
        annotations = {table: current[table] for table in ("events", "reviews")}
        predictions = self.store.predictions(experiment_id)
        predictions_changed = len(predictions) != len(report["rows"])
        annotations_changed = digest(annotations) != report["annotation_hash"]
        # Legacy reports did not include revision=0 in their annotation hashes.
        if annotations_changed and all(row["revision"] == 0 for rows in annotations.values() for row in rows):
            legacy = {kind: [{k: v for k, v in row.items() if k != "revision"} for row in rows]
                      for kind, rows in annotations.items()}
            annotations_changed = digest(legacy) != report["annotation_hash"]
        return {"has_report": True, "stale": predictions_changed or annotations_changed,
                "predictions_changed": predictions_changed, "annotations_changed": annotations_changed}
