import csv
import io
import json

from backend.contracts import CLASSES


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def export_report(report, format):
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False), "application/json"
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["prediction_id", "timestamp", "horizon", *CLASSES, "label", "reason", "hash", "generated_at", "revealed_at"])
        for row in report["rows"]:
            writer.writerow([row["id"], row["timestamp"], row["horizon"],
                             *(row["probabilities"][k] for k in CLASSES), row["label"], row["reason"],
                             row["hash"], row["generated_at"], report["revealed_at"]])
        return output.getvalue(), "text/csv"
    entries = []
    for index, row in enumerate(report["rows"], 1):
        probabilities = " | ".join(f"{k}: {v:.1%}" for k, v in row["probabilities"].items())
        entries.append(f"{index}\n{srt_time(row['timestamp'])} --> {srt_time(row['timestamp'] + min(4, row['horizon']))}\nPREVISÃO REGISTRADA · {probabilities}\n")
    # Outcomes remain in the report. Never insert them into prediction subtitles.
    return "\n".join(entries), "application/x-subrip"
