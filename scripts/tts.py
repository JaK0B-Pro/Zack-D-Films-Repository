import json, sys, os, soundfile as sf
from kokoro_onnx import Kokoro
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
models = sys.argv[1]
voice = sys.argv[2] if len(sys.argv) > 2 else "am_michael"
k = Kokoro(f"{models}/kokoro-v1.0.onnx", f"{models}/voices-v1.0.bin")
lines = json.load(open(f"{root}/scripts/script.json"))
timing = []
for l in lines:
    samples, sr = k.create(l["text"], voice=voice, speed=1.12, lang="en-us")
    path = f"{root}/audio/{l['id']}.wav"
    sf.write(path, samples, sr)
    timing.append({"id": l["id"], "text": l["text"], "dur": len(samples) / sr})
    print(l["id"], round(len(samples) / sr, 2))
json.dump(timing, open(f"{root}/audio/timing.json", "w"), indent=1)
