"""Shared timeline: scene order, start times and key event frames (must match scenes.py)."""
import json, os, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 24
PAD = 0.45
VO_OFFSET = 0.15  # narration starts this long after its scene cuts in
ORDER = ["hook", "speed", "perm", "temp", "movies", "adren", "artery", "shock", "tq", "bullet"]

TIMING = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "audio", "timing.json")))}


def nframes(sid):
    return round((TIMING[sid]["dur"] + PAD) * FPS)


def scenes():
    out, f = [], 0
    for sid in ORDER:
        n = nframes(sid)
        out.append({"id": sid, "start": f, "frames": n, "text": TIMING[sid]["text"], "dur": TIMING[sid]["dur"]})
        f += n
    return out


def heartbeat_frames(F):
    """Mirror of the beat keyframes in scene_shock."""
    half, f, period, beats = F // 2, 1, 18.0, []
    while f < half + 2:
        beats.append(int(f))
        f += period
        period = max(9.0, period * 0.85)
    return beats


def events():
    """(scene_id, local_frame, kind) for sound effects and flashes."""
    ev = []
    s = {x["id"]: x for x in scenes()}
    ev.append(("hook", 1, "gunshot"))
    ev.append(("hook", 30, "whoosh"))
    ev.append(("speed", 2, "crack"))
    for sid in ("perm", "temp"):
        F = s[sid]["frames"]
        ev.append((sid, round(F * 0.18), "impact"))
    ev.append(("temp", round(s["temp"]["frames"] * 0.18) + 4, "stretch"))
    F = s["movies"]["frames"]
    ev.append(("movies", round(F * 0.42), "rise"))
    ev.append(("adren", round(s["adren"]["frames"] * 0.2), "shimmer"))
    F = s["artery"]["frames"]
    ev.append(("artery", round(F * 0.3), "impact"))
    ev.append(("artery", round(F * 0.3) + 3, "gush"))
    for b in heartbeat_frames(s["shock"]["frames"]):
        ev.append(("shock", b, "heartbeat"))
    ev.append(("shock", s["shock"]["frames"] // 2, "whoosh"))
    F = s["tq"]["frames"]
    t0, t1 = round(F * 0.3), round(F * 0.55)
    for f in range(t0, t1, 3):
        ev.append(("tq", f, "click"))
    ev.append(("bullet", 1, "xray"))
    for sc in scenes()[1:]:
        ev.append((sc["id"], 0, "swish"))
    return ev
