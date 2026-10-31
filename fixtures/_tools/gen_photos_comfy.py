"""Generate candidate synthetic vehicle photos through a local ComfyUI REST API (no cloud).

Usage: python gen_photos_comfy.py <outdir> <label>:<count> ...   e.g.  front:4 rear:4 side:2
Candidates land in <outdir>/<label>_<n>.png. A human (or Claude) must LOOK at every image
and record what it actually shows in fixtures/manifest.json; prompts are not ground truth.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8188"
CKPT = "Realistic_Vision_V5.1_fp16-no-ema.safetensors"
BASE = "photo of a small silver hatchback car parked on an asphalt street, overcast daylight, "
PROMPTS = {
    "front": BASE + "front three-quarter view, front end badly damaged in a collision, crumpled bumper, dented bonnet, "
                    "broken headlight, scattered debris, insurance claim photo, realistic, sharp focus",
    "rear": BASE + "rear three-quarter view from behind, rear end badly damaged in a collision, crumpled rear bumper, "
                   "dented boot lid, broken tail light, insurance claim photo, realistic, sharp focus",
    "front2": BASE + "front view of a wrecked car after a head-on crash, front end smashed in, hood crumpled and folded up, "
                     "bumper torn off hanging, headlight missing, crushed fender, bent metal, severe collision damage, "
                     "accident scene photo, realistic",
    "rear2": BASE + "rear view of a wrecked car after being rear-ended, rear end smashed in, trunk lid crumpled and bent, "
                    "bumper torn off hanging, tail light shattered, crushed rear panel, bent metal, severe collision damage, "
                    "accident scene photo, realistic",
    "side2": "photo of a small silver hatchback car parked on an asphalt street, overcast daylight, exact side profile view, "
             "camera facing the driver's door, whole car visible, orthographic side elevation, both wheels visible, undamaged, "
             "no dents, intact bodywork, insurance inspection photo, realistic",
    "side": BASE + "clean side profile view, completely undamaged intact car, no dents, insurance inspection photo, "
                   "realistic, sharp focus",
}
NEG = "cartoon, anime, illustration, painting, text, watermark, logo, people, blurry, deformed, multiple cars, lowres"


def workflow(prompt: str, seed: int, w: int = 640, h: int = 480, steps: int = 22) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                    "latent_image": ["4", 0], "seed": seed, "steps": steps, "cfg": 6.5,
                                                    "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "verity_fx"}},
    }


def post(path: str, obj: dict) -> dict:
    req = urllib.request.Request(HOST + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def run_one(prompt: str, seed: int, out: Path) -> None:
    pid = post("/prompt", {"prompt": workflow(prompt, seed)})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 600:
        hist = json.load(urllib.request.urlopen(f"{HOST}/history/{pid}", timeout=30))
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st)[:500])
            img = hist[pid]["outputs"]["7"]["images"][0]
            url = f"{HOST}/view?filename={img['filename']}&subfolder={img['subfolder']}&type={img['type']}"
            out.write_bytes(urllib.request.urlopen(url, timeout=60).read())
            return
        time.sleep(3)
    raise TimeoutError("ComfyUI job exceeded 10 minutes")


if __name__ == "__main__":
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    seed0 = 1000
    for spec in sys.argv[2:]:
        label, count = spec.split(":")
        for n in range(int(count)):
            dest = outdir / f"{label}_{n}.png"
            if dest.exists():
                continue
            t = time.time()
            run_one(PROMPTS[label], seed0 + n * 17 + len(label), dest)
            print(f"{dest.name} done in {time.time() - t:.0f}s", flush=True)
