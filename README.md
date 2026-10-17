# What Happens When You Get Shot — 3D animated Short

A Zack D. Films–style educational 3D short (1080×1920, 24 fps, ~67 s), made entirely in code:

| Step | Tool | File |
|------|------|------|
| Script + narration | Kokoro neural TTS (voice `am_michael`) | `scripts/script.json`, `scripts/tts.py` |
| 3D animation | Blender 5.2 (`bpy`, Cycles) | `scripts/blib.py`, `scripts/scenes.py` |
| Music + sound effects | Synthesised with NumPy/SciPy | `scripts/audio.py`, `scripts/timeline.py` |
| Captions, labels, encode | Pillow + FFmpeg (H.264, −14 LUFS) | `scripts/compose.py` |

Final video: `output/short.mp4`

## Rebuild

```bash
pip install bpy kokoro-onnx soundfile scipy pillow numpy
# models: kokoro-v1.0.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx/releases
python3 scripts/tts.py /path/to/models am_michael     # narration -> audio/*.wav + timing.json
scripts/render_all.sh hook speed perm temp movies adren artery shock tq bullet   # ~1-2 h on 4 CPU cores
python3 scripts/audio.py                               # audio/mix.wav
python3 scripts/compose.py                             # output/short.mp4
```

Preview a single frame of a scene: `python3 scripts/scenes.py perm 90` → `renders/perm/preview_0090.png`.

## Script & fact check

| # | Line | Basis |
|---|------|-------|
| 1 | This is what happens inside your body when you get shot. | Hook |
| 2 | A handgun bullet travels ~1,200 ft/s, faster than sound. | 9 mm muzzle velocity ≈ 1,150–1,250 ft/s; speed of sound ≈ 1,125 ft/s |
| 3 | It crushes tissue in its path → **permanent cavity** | Standard wound-ballistics definition (tissue crush) |
| 4 | It shoves tissue outward → **temporary cavity**, collapses in milliseconds | Tissue stretch; elastic muscle tolerates it, solid organs (liver, spleen, brain) tear more easily |
| 5 | You won't fly backwards; less momentum than a fastball | 8 g × 370 m/s ≈ 3 kg·m/s vs 145 g × 40 m/s ≈ 6 kg·m/s |
| 6 | Adrenaline can mask the pain at first | Widely reported by survivors / trauma literature |
| 7 | Blood loss is the real danger; femoral artery bleed can kill in minutes | First-aid sources range from ~90 s to <5 min; hemorrhage is the leading preventable trauma death |
| 8 | Heart races, brain starved of oxygen → hemorrhagic shock | Compensatory tachycardia, reduced perfusion |
| 9 | Tourniquet a few inches above the wound | Stop the Bleed / TCCC guidance: 2–3 in (5–7.5 cm) above the wound |
| 10 | Doctors often leave bullets in | Removal is skipped when it would cause more damage than leaving the fragment |

Sources:
- [Review of ballistic pressure wave experiments (arXiv)](https://arxiv.org/pdf/physics/0701268)
- [DTIC wound ballistics report](https://apps.dtic.mil/sti/pdfs/ADA570804.pdf)
- [Wound ballistics — WikEM](https://harborucla.wikem.org/wiki/Wound_Ballistics)
- [Basic wound ballistic terminal performance facts](https://primaryandsecondary.com/basic-wound-ballistic-terminal-performance-facts/)
- [First aid: bleeding](https://fhn.gov.az/en/education/first-aid/bleeding)
- [When to use a tourniquet](https://www.c2cfirstaidaquatics.com/how-do-you-know-when-to-use-a-tourniquet/)
- [More U.S. gunshot victims dying before reaching a hospital (UW)](https://newsroom.uw.edu/news/more-us-gunshot-victims-dying-reaching-hospital)
- [How do people survive gunshot wounds? (Live Science)](https://www.livescience.com/21774-bullet-gunshot-wound-survive.html)

## YouTube upload kit

**Title:** What Happens Inside Your Body When You Get Shot 😳 #shorts

**Description:**
> A 3D animation of what a bullet actually does inside the body: the permanent and temporary cavity, why you don't fly backwards like in the movies, why blood loss is the real danger, and how a tourniquet saves lives.
> Educational content only. Learn bleeding control at stopthebleed.org.
> #shorts #3danimation #science #anatomy #humanbody #education

**Tags:** 3d animation, human body, anatomy, science, education, wound ballistics, first aid, stop the bleed, tourniquet, how the body works

### Keeping it YouTube-safe
- The video is **educational and non-graphic**: stylised anatomy, no real people, no real footage, no weapons being fired at anyone on screen. That fits YouTube's EDSA (educational) exception to the violent/graphic content policy.
- Keep the first frame/thumbnail as the **bullet or the anatomy**, not a person being shot.
- Don't use a sensational title like "shooting a guy". Phrase it as an educational "what happens inside your body".
- If YouTube age-restricts it anyway, appeal and point to the educational context. The first-aid ending helps here.
