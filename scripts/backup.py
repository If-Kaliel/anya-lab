"""Create or restore a verified local snapshot of recordings and the SQLite database."""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def checksum(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def checked_file(root, name):
    if name != "anya.sqlite3" and not re.fullmatch(r"videos/[0-9a-f]{32}\.(mp4|mkv)", name):
        raise ValueError("Caminho não autorizado no backup")
    path = root / name
    if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Links ou caminhos externos não são aceitos no backup")
    if not path.is_file():
        raise ValueError("Arquivo do backup ausente")
    return path


def read_only(database):
    return sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)


def publish_directory(staging, target):
    # OneDrive/Windows indexing can briefly hold a newly written directory.
    # Retry only sharing/access failures; never replace an existing destination.
    for attempt in range(5):
        if target.exists():
            raise ValueError("A pasta de destino já existe")
        try:
            staging.rename(target)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 4:
                raise
            time.sleep(.05 * 2 ** attempt)


def validate_database(root):
    db = read_only(checked_file(root, "anya.sqlite3"))
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Banco SQLite inválido")
        videos = [json.loads(row[0]) for row in db.execute("SELECT payload FROM videos")]
        for video in videos:
            path = checked_file(root, f"videos/{video['stored_name']}")
            if checksum(path) != video["sha256"]:
                raise ValueError("A gravação não corresponde ao hash registrado no banco")
        return videos
    finally:
        db.close()


def create_backup(data_dir, output):
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(data_dir):
        raise ValueError("Escolha uma pasta nova fora da pasta de dados para o backup")
    source = checked_file(data_dir, "anya.sqlite3")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".anya-backup-", dir=output.parent))
    try:
        db, target = read_only(source), sqlite3.connect(staging / "anya.sqlite3")
        try:
            # SQLite online backup includes committed WAL state, even with the app open.
            db.backup(target)
            videos = [json.loads(row[0]) for row in target.execute("SELECT payload FROM videos")]
        finally:
            target.close(); db.close()
        (staging / "videos").mkdir()
        files = ["anya.sqlite3"]
        for video in videos:
            relative = f"videos/{video['stored_name']}"
            shutil.copyfile(checked_file(data_dir, relative), staging / relative)
            files.append(relative)
        validate_database(staging)
        manifest = {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(),
                    "scope": ["database", "original_recordings"],
                    "files": {name: {"sha256": checksum(staging / name), "bytes": (staging / name).stat().st_size} for name in files}}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if output.exists():
            raise ValueError("A pasta de destino já existe")
        publish_directory(staging, output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def restore_backup(backup, target):
    backup, target = Path(backup).resolve(), Path(target).resolve()
    if target.exists() or target.is_relative_to(backup):
        raise ValueError("Restaure em uma pasta nova; nenhum dado existente será sobrescrito")
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("files"), dict) or "anya.sqlite3" not in manifest["files"]:
        raise ValueError("Manifesto de backup incompatível")
    for name, expected in manifest["files"].items():
        path = checked_file(backup, name)
        if checksum(path) != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise ValueError("Falha de integridade no backup")
    videos = validate_database(backup)
    if any(f"videos/{v['stored_name']}" not in manifest["files"] for v in videos):
        raise ValueError("Manifesto não inclui todas as gravações do banco")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".anya-restore-", dir=target.parent))
    try:
        (staging / "videos").mkdir()
        for name in manifest["files"]:
            shutil.copyfile(checked_file(backup, name), staging / name)
            if checksum(staging / name) != manifest["files"][name]["sha256"]:
                raise ValueError("Arquivo mudou durante a restauração")
        validate_database(staging)
        if target.exists():
            raise ValueError("A pasta de destino já existe")
        publish_directory(staging, target)
        return {"recordings": len(videos), "files": len(manifest["files"])}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--data-dir", type=Path, default=Path("data"))
    create.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = create_backup(args.data_dir, args.output) if args.command == "create" else restore_backup(args.backup, args.target)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Backup não concluído: {exc}\n")
    print(json.dumps(result, indent=2))
