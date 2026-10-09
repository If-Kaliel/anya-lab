"""Recording identity supplied by the researcher, independent of file encoding."""
import math


def source_id(video):
    return video.get("source_match_id", video["id"])


def normalize_source(value, fallback):
    value = value.strip().casefold() if value else fallback
    if len(value) > 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Identificador de partida inválido; use até 128 caracteres sem controles")
    return value


def validate_source(existing, candidate):
    offset = candidate.get("source_offset", 0)
    if not math.isfinite(offset) or offset < 0:
        raise ValueError("Início do trecho deve ser finito e não negativo")
    for video in existing:
        if source_id(video) != source_id(candidate):
            continue
        if video["split"] != candidate["split"]:
            raise ValueError("Vazamento: trechos da mesma partida devem permanecer no mesmo split")
        if video["synthetic"] != candidate["synthetic"]:
            raise ValueError("Uma partida não pode misturar gravações reais e sintéticas")
        start = video.get("source_offset", 0)
        if offset < start + video["duration"] - 1e-6 and start < offset + candidate["duration"] - 1e-6:
            raise ValueError("Trechos sobrepostos da mesma partida duplicariam amostras; escolha um trecho sem sobreposição")
