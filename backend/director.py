"""Synchronized call exports distinguish recorded text from actual playback."""
import csv
import io
import json

from backend.storage import canonical


def srt_time(seconds):
    total = round(seconds * 1000)
    hours, total = divmod(total, 3600000)
    minutes, total = divmod(total, 60000)
    seconds, milliseconds = divmod(total, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'


def export_calls(store, research, voice, experiment_id, format):
    exp = store.experiment(experiment_id)
    calls = research.records('calls', experiment_id)
    jobs = {j['id']: j for j in voice.history()}
    rows = [{**call, 'phase': 'pre_outcome_decision', 'mode': exp['mode'],
             'voice': jobs.get(call.get('voice_job_id'))} for call in calls]
    if format == 'json':
        return canonical({'schema_version': 'director-1.0', 'experiment_id': experiment_id,
                          'mode': exp['mode'], 'calls': rows, 'notice': 'Decision time is not playback time. Playback events record actual browser playback.'}), 'application/json'
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['timestamp', 'expires_at', 'category', 'priority', 'decision', 'text', 'prediction_hash', 'mode', 'voice_state', 'playback_completed'])
        for r in rows:
            job = r['voice'] or {}
            writer.writerow([r[k] for k in ('timestamp', 'expires_at', 'category', 'priority', 'decision', 'text', 'prediction_hash', 'mode')] +
                            [job.get('state', 'not_generated'), any(e['state'] == 'completed' for e in job.get('playback_events', []))])
        return output.getvalue(), 'text/csv'
    blocks = []
    # Only actual replay playback starts are timed captions; no silent invention of voice timeline.
    for row in rows:
        job = row['voice'] or {}
        for event in job.get('playback_events', []):
            start = event.get('replay_timestamp')
            if event['state'] == 'started' and start is not None:
                end = min(row['expires_at'], start + job.get('measurement', {}).get('duration', 3))
                if end > start:
                    blocks.append(f'{len(blocks)+1}\n{srt_time(start)} --> {srt_time(end)}\n[{row["mode"]} / {row["category"]}] {row["text"]}\n')
    return '\n'.join(blocks), 'application/x-subrip'
