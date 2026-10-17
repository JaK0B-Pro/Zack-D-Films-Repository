"""Upscales the Blender frames to 1080x1920, adds captions/labels/flashes and encodes the final Short.

Usage: python3 scripts/compose.py [output.mp4] [--scenes id,id] [--still scene:frame]
"""
import os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
import timeline as T

W, H = 1080, 1920
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
YELLOW = (255, 214, 0)
RED = (255, 70, 60)
BLUE = (90, 180, 255)
f_cap = ImageFont.truetype(FONT, 92)
f_lab = ImageFont.truetype(FONT, 64)
f_big = ImageFont.truetype(FONT, 130)
f_small = ImageFont.truetype(FONT, 46)

yy, xx = np.mgrid[0:H, 0:W]
VIGNETTE = (1 - 0.45 * (((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)).clip(0.35, 1)[..., None].astype(np.float32)


# ---------------------------------------------------------------- captions

def word_times(text, dur):
    """Approximate per-word timing from character counts plus punctuation pauses."""
    words = text.split()
    weights, pauses = [], []
    for w in words:
        weights.append(len(re.sub(r"[^\w]", "", w)) + 1.5)
        pauses.append(4.0 if w[-1] in ".!?" else 2.5 if w[-1] in ",;:" else 0.0)
    total = sum(weights) + sum(pauses[:-1])
    lead, tail = 0.08, 0.15
    unit = (dur - lead - tail) / total
    t, out = lead, []
    for w, wt, p in zip(words, weights, pauses):
        out.append((w, t, t + wt * unit))
        t += (wt + p) * unit
    return out


def chunks(wt):
    """Group words into 1-3 word caption cards, breaking at punctuation."""
    out, cur = [], []
    for w in wt:
        cur.append(w)
        chars = sum(len(x[0]) for x in cur)
        if len(cur) == 3 or chars >= 13 or w[0][-1] in ".,!?;:":
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def draw_text(d, xy, text, font, fill, stroke=10, anchor="mm"):
    d.text((xy[0] + 5, xy[1] + 7), text, font=font, fill=(0, 0, 0, 150), anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
    d.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def draw_caption(d, card, t):
    # pop-in scale is faked by a tiny upward settle
    words = [w[0].upper() for w in card]
    widths = [d.textlength(w, font=f_cap) for w in words]
    space = 26
    total = sum(widths) + space * (len(words) - 1)
    if total > W - 120:  # wrap long cards onto two lines
        lines = [card[:2], card[2:]] if len(card) == 3 else [card[:1], card[1:]]
    else:
        lines = [card]
    y0 = 1300 - (len(lines) - 1) * 55
    for li, line in enumerate(lines):
        ws = [w[0].upper() for w in line]
        wd = [d.textlength(w, font=f_cap) for w in ws]
        x = W / 2 - (sum(wd) + space * (len(ws) - 1)) / 2
        for (w, a, b), txt, wdt in zip(line, ws, wd):
            active = a <= t < b + 0.12
            col = YELLOW if active else (255, 255, 255)
            draw_text(d, (x + wdt / 2, y0 + li * 110), txt, f_cap, col)
            x += wdt + space


def label(d, text, y=260, color=(255, 255, 255), font=None):
    draw_text(d, (W / 2, y), text, font or f_lab, color, stroke=9)


def lerp(a, b, x):
    x = max(0.0, min(1.0, x))
    return a + (b - a) * x


# ---------------------------------------------------------------- per-scene overlays

def overlays(d, sid, f, F):
    """f: local frame index (1-based), F: scene length."""
    if sid == "speed":
        v = int(lerp(0, 1200, (f - 8) / 30))
        label(d, f"{v:,} ft/s", 300, YELLOW, f_big)
        label(d, "≈ 370 m/s", 420, (255, 255, 255), f_small)
        if f > F * 0.55:
            label(d, "SPEED OF SOUND: 1,125 ft/s", 500, BLUE, f_small)
    elif sid == "perm" and f > F * 0.35:
        label(d, "PERMANENT CAVITY", 280, RED)
    elif sid == "temp":
        hit, out = round(F * 0.18), round(F * 0.62)
        if f > hit + 2:
            label(d, "TEMPORARY CAVITY", 280, YELLOW)
            ms = lerp(0, 5.0, (f - hit) / (out + 34 - hit))
            label(d, f"{ms:.2f} ms", 390, (255, 255, 255), f_small)
    elif sid == "movies":
        label(d, "MOMENTUM", 260, (255, 255, 255))
    elif sid == "adren" and f > F * 0.2:
        label(d, "ADRENALINE", 280, (255, 170, 40))
    elif sid == "artery":
        label(d, "FEMORAL ARTERY", 280, (255, 255, 255))
        if f > F * 0.3 + 6:
            label(d, "BLOOD LOSS", 390, RED, f_small)
    elif sid == "shock":
        if f < F // 2:
            bpm = int(lerp(80, 150, f / (F / 2)))
            label(d, "HEART RATE", 260, (255, 255, 255))
            label(d, f"{bpm} BPM ▲", 370, RED, f_small)
        else:
            label(d, "BRAIN OXYGEN ▼", 260, BLUE)
    elif sid == "tq":
        label(d, "TOURNIQUET", 260, YELLOW)
        label(d, "2–3 INCHES ABOVE THE WOUND", 370, (255, 255, 255), f_small)
    elif sid == "bullet":
        label(d, "X-RAY", 260, BLUE)


def movies_side_labels(d, f, F):
    if f > F * 0.42 + 18:
        for x, name, val, col in ((W * 0.27, "BULLET", "~3 kg·m/s", (255, 150, 60)),
                                  (W * 0.73, "FASTBALL", "~6 kg·m/s", (90, 170, 255))):
            draw_text(d, (x, 1560), name, f_small, col, stroke=8)
            draw_text(d, (x, 1625), val, f_small, (255, 255, 255), stroke=8)


def flash_amount(sid, f, F):
    hits = {"hook": [1], "perm": [round(F * 0.18)], "temp": [round(F * 0.18)], "artery": [round(F * 0.3)]}
    a = 0.0
    for h in hits.get(sid, []):
        if h <= f < h + 5:
            a = max(a, (0.85 if sid == "hook" else 0.5) * (1 - (f - h) / 5))
    return a


# ---------------------------------------------------------------- frames

def frame_image(sid, f, F, cards):
    path = os.path.join(T.ROOT, "renders", sid, f"{f:04d}.png")
    if os.path.exists(path):
        im = Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    else:
        im = Image.new("RGB", (W, H), (20, 0, 0))
    a = np.asarray(im).astype(np.float32) * VIGNETTE
    fl = flash_amount(sid, f, F)
    if fl:
        a = a * (1 - fl) + 255 * fl
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    overlays(d, sid, f, F)
    if sid == "movies":
        movies_side_labels(d, f, F)
    t = (f - 1) / T.FPS - T.VO_OFFSET
    for card in cards:
        if card[0][1] - 0.05 <= t < card[-1][2] + 0.25:
            # keep a card up until the next one starts
            draw_caption(d, card, t)
            break
    return im


def scene_cards(s):
    cards = chunks(word_times(s["text"], s["dur"]))
    # extend each card to the next card's start so captions never flicker off mid-line
    for i in range(len(cards) - 1):
        nxt = cards[i + 1][0][1]
        w, a, b = cards[i][-1]
        cards[i][-1] = (w, a, max(b, nxt - 0.26))
    return cards


def main():
    args = sys.argv[1:]
    out = os.path.join(T.ROOT, "output", "short.mp4")
    only = None
    if args and args[0].endswith(".mp4"):
        out = args.pop(0)
    if "--still" in args:
        sid, fr = args[args.index("--still") + 1].split(":")
        s = {x["id"]: x for x in T.scenes()}[sid]
        frame_image(sid, int(fr), s["frames"], scene_cards(s)).save(os.path.join(T.ROOT, "output", f"still_{sid}_{fr}.png"))
        return
    if "--scenes" in args:
        only = args[args.index("--scenes") + 1].split(",")
    sc = [s for s in T.scenes() if only is None or s["id"] in only]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    audio = os.path.join(T.ROOT, "audio", "mix.wav")
    a_start = sc[0]["start"] / T.FPS
    dur = sum(s["frames"] for s in sc) / T.FPS
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-",
           "-ss", f"{a_start:.3f}", "-t", f"{dur:.3f}", "-i", audio,
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-movflags", "+faststart",
           "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for s in sc:
        cards = scene_cards(s)
        for f in range(1, s["frames"] + 1):
            p.stdin.write(frame_image(s["id"], f, s["frames"], cards).tobytes())
        print("composed", s["id"], flush=True)
    p.stdin.close()
    p.wait()
    print("wrote", out)


if __name__ == "__main__":
    main()
