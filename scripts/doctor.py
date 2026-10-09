"""Read-only installation diagnostics for the local Anya laboratory."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def diagnose(root):
    checks = [{"name": "Python 3.12+", "ok": sys.version_info >= (3, 12), "detail": sys.version.split()[0]}]
    for module in ("fastapi", "pydantic", "numpy", "cv2", "uvicorn", "sklearn"):
        available = importlib.util.find_spec(module) is not None
        checks.append({"name": module, "ok": available, "detail": "Disponível" if available else "Execute scripts/setup.ps1"})
    for name in ("ffmpeg", "ffprobe", "node", "npm"):
        command = os.getenv(f"ANYA_{name.upper()}", name)
        if name == "npm" and os.name == "nt":
            command = "npm.cmd"
        try:
            result = subprocess.run([command, "-version" if name.startswith("ff") else "--version"], capture_output=True, text=True, timeout=10)
            detail = result.stdout.splitlines()[0] if result.stdout else "Não respondeu"
            checks.append({"name": name, "ok": result.returncode == 0, "detail": detail})
        except (OSError, subprocess.TimeoutExpired):
            checks.append({"name": name, "ok": False, "detail": "Executável indisponível no PATH"})
    built = (root / "frontend/dist/index.html").is_file()
    checks.append({"name": "Dashboard compilado", "ok": built, "detail": "Pronto" if built else "Execute scripts/setup.ps1"})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = diagnose(Path(__file__).resolve().parent.parent)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for check in report["checks"]:
            print(f"{'OK' if check['ok'] else 'FALHA'} · {check['name']}: {check['detail']}")
    sys.exit(0 if report["ok"] else 1)
