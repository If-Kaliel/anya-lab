import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from backend.contracts import CLASSES
from backend.export import srt_time
from backend.human_lab import HumanLab, StudyInput
from backend.storage import digest


def export_study(report, format):
    if format == 'json':
        return json.dumps(report, indent=2, ensure_ascii=False), 'application/json'
    if format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['round', 'timestamp', 'horizon', 'mode', 'participant_id', 'abstain',
            *['human_'+c for c in CLASSES], *['ai_'+c for c in CLASSES], 'label', 'reason',
            'human_hash', 'ai_hash', 'context_hash', 'submitted_at', 'ai_generated_at', 'revealed_at'])
        for row in report['rows']:
            human, ai = row['human'], row['ai']
            writer.writerow([row['round_index'], row['timestamp'], row['horizon'], report['mode'], human['participant_id'],
                human['abstain'], *[(human['probabilities'] or {}).get(c) for c in CLASSES],
                *[ai['probabilities'][c] for c in CLASSES], row['label'], row['reason'], human['hash'], ai['hash'],
                row['context_hash'], human['submitted_at'], ai['generated_at'], report['revealed_at']])
        return output.getvalue(), 'text/csv'
    entries = []
    for row in report['rows']:
        human = 'ABSTENÇÃO' if row['human']['abstain'] else ' | '.join(f'{c}: {row["human"]["probabilities"][c]:.1%}' for c in CLASSES)
        ai = ' | '.join(f'{c}: {row["ai"]["probabilities"][c]:.1%}' for c in CLASSES)
        entries.append((row['timestamp'], row['timestamp']+row['horizon'],
            f'{report["mode"]} · PREVISÕES BLOQUEADAS ANTES DA REVELAÇÃO\nHUMAN: {human}\nANYA: {ai}'))
        # Outcomes are a separate post-horizon overlay, never prediction text.
        entries.append((row['timestamp']+row['horizon'], row['timestamp']+row['horizon']+2,
            f'{report["mode"]} · RESULTADO ANOTADO POSTERIOR: {row["label"] or row["reason"]}'))
    return '\n'.join(f'{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n'
        for i,(start,end,text) in enumerate(sorted(entries),1)), 'application/x-subrip'


def install_lab(app, store, engine, frames):
    lab = HumanLab(store, engine, frames)
    app.state.lab = lab
    router = APIRouter(prefix='/api/lab/studies')

    @router.get('')
    def studies():
        return lab.studies()

    @router.post('', status_code=201)
    def create(command: StudyInput):
        return lab.create(command)

    @router.post('/{study_id}/invite')
    def invite(study_id: str):
        token = lab.invite(study_id)
        return {'url':f'http://127.0.0.1:8001/#trial={token}'}

    @router.post('/{study_id}/reveal', status_code=201)
    def reveal(study_id: str):
        return lab.reveal(study_id)

    @router.get('/{study_id}/reports')
    def reports(study_id: str):
        lab.study(study_id)
        with store.connect() as db:
            rows = list(db.execute('SELECT id FROM lab_reports WHERE study_id=? ORDER BY id DESC', (study_id,)))
        return [{'report_id':row[0], 'revealed_at':lab.report(study_id,row[0])['revealed_at']} for row in rows]

    @router.get('/{study_id}/report')
    def report(study_id: str, report_id: int | None = Query(None, ge=1)):
        lab.study(study_id)
        return lab.report(study_id,report_id)

    @router.get('/{study_id}/report-status')
    def status(study_id: str):
        study = lab.study(study_id)
        report = lab.report(study_id)
        annotations = store.annotation_snapshot(study['video_id'])
        current = digest({k:annotations[k] for k in ('events','reviews')})
        return {'stale':bool(report and report['annotation_hash'] != current), 'annotation_hash':current}

    @router.get('/{study_id}/export/{format}')
    def export(study_id: str, format: Literal['json','csv','srt'], report_id: int = Query(..., ge=1)):
        lab.study(study_id)
        body, media_type = export_study(lab.report(study_id,report_id),format)
        return Response(body, media_type=media_type, headers={'Content-Disposition':f'attachment; filename="anya-duel-{study_id}-r{report_id}.{format}"'})

    app.include_router(router)
