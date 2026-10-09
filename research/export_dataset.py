"""Export reviewed temporal samples without putting future labels into features."""
import argparse
import json
from pathlib import Path

from backend.evaluation import resolve
from backend.experiments import now
from backend.features import FEATURE_ORDER, temporal_features
from backend.provenance import source_id, validate_source
from backend.storage import Store, digest
from backend.temporal import snapshot


def build_dataset(store, synthetic=False):
    with store.connect() as db:
        videos = [json.loads(row[0]) for row in db.execute("SELECT payload FROM videos ORDER BY id")]
    selected = [v for v in videos if v["synthetic"] == synthetic]
    samples, provenance, exclusions = [], [], {}
    for index, video in enumerate(selected):
        validate_source(selected[:index], video)
        annotations = store.annotation_snapshot(video["id"])
        provenance.append({"video_id": video["id"], "source_match_id": source_id(video),
                           "source_identity": video.get("source_identity", "legacy_unique_recording"),
                           "split": video["split"], "video_sha256": video["sha256"],
                           "annotation_hash": digest(annotations)})
        timestamp = 0
        while timestamp + 15 <= video["duration"]:
            label, reason = resolve(annotations["events"], annotations["reviews"], timestamp)
            if label is None:
                exclusions[reason] = exclusions.get(reason, 0) + 1
            else:
                # Only the observation channel enters this immutable capability.
                features, observed = temporal_features(snapshot(annotations["observations"], timestamp))
                samples.append({"match_id": source_id(video), "video_id": video["id"],
                                "source_match_id": source_id(video), "split": video["split"],
                                "timestamp": timestamp, "source_timestamp": video.get("source_offset", 0) + timestamp,
                                "features": features, "feature_observed": observed, "label": label})
            timestamp += 5
    return {"schema_version": "1.0", "generated_at": now(), "data_mode": "technical_demo" if synthetic else "real_recordings",
            "feature_order": FEATURE_ORDER, "feature_version": "manual-confidence-10s-v1", "seed": 42,
            "step": 5, "horizon": 15, "samples": samples, "provenance": provenance,
            "diagnostics": {"recordings": len(selected), "samples": len(samples), "excluded": exclusions,
                            "samples_without_features": sum(not any(s["feature_observed"]) for s in samples)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("exports/training-dataset.json"))
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    if not (args.data_dir / "anya.sqlite3").is_file():
        parser.error("Banco local não encontrado")
    dataset = build_dataset(Store(args.data_dir), args.synthetic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dataset["diagnostics"], indent=2))
