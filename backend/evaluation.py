import math

from backend.contracts import CLASSES


def resolve(events, reviews, timestamp, horizon=15, tolerance=0.1):
    end = timestamp + horizon
    # A reviewed full interval is required even for a positive outcome.
    if not any(r["reliable"] and r["start"] <= timestamp and r["end"] >= end for r in reviews):
        return None, "interval_not_reviewed"
    inside = sorted((e for e in events if timestamp < e["timestamp"] <= end), key=lambda e: e["timestamp"])
    if not inside:
        return "none", "reviewed_no_visible_elimination"
    first = inside[0]
    simultaneous = [e for e in inside if e["timestamp"] - first["timestamp"] <= tolerance]
    if any(not e["reliable"] or e["team"] == "unknown" for e in simultaneous):
        return None, "ambiguous_first_event"
    if len({e["team"] for e in simultaneous}) > 1:
        return None, "simultaneous_opposite_teams"
    return ("ally_first" if first["team"] == "ally" else "enemy_first"), "visible_first_event"


def metrics(rows):
    evaluated = [r for r in rows if r["label"] is not None]
    matrix = [[0] * 3 for _ in CLASSES]
    correct = brier = loss = latency = unknown = 0.0
    bins = [[] for _ in range(5)]
    for row in evaluated:
        p = [row["probabilities"][k] for k in CLASSES]
        actual = CLASSES.index(row["label"])
        predicted = max(range(3), key=lambda i: p[i])
        matrix[actual][predicted] += 1
        hit = int(actual == predicted)
        correct += hit
        brier += sum((value - int(i == actual)) ** 2 for i, value in enumerate(p))
        loss -= math.log(max(p[actual], 1e-15))
        latency += row["latency_ms"]
        unknown += row["unknown_rate"]
        bins[min(int(max(p) * 5), 4)].append((max(p), hit))
    n = len(evaluated)
    return {"evaluated": n, "excluded": len(rows) - n, "classes": CLASSES,
            "accuracy": correct / n if n else None,
            "brier_score": brier / n if n else None,
            "log_loss": loss / n if n else None,
            "confusion_matrix": matrix,
            "mean_latency_ms": latency / n if n else None,
            "unknown_rate": unknown / n if n else None,
            "calibration": [{"bin": i, "count": len(b), "confidence": sum(x[0] for x in b) / len(b),
                             "accuracy": sum(x[1] for x in b) / len(b)} for i, b in enumerate(bins) if b] if n >= 30 else None}
