"""Live Gemini preflight: lists models, then makes one JSON call. Never prints the key."""
import json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

env = {}
for line in (Path(__file__).resolve().parents[1] / "backend" / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
key = env.get("GEMINI_API_KEY", "")
model = env.get("GEMINI_MODEL", "gemini-3.8-flash")
print("key present:", bool(key), "len:", len(key), "model:", model)
BASE = "https://generativelanguage.googleapis.com/v1beta"


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read()), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400], time.time() - t
    except Exception as e:  # noqa
        return -1, repr(e), time.time() - t


st, data, dt = call("GET", f"{BASE}/models?pageSize=200")
print("list models:", st, f"{dt:.1f}s")
if st == 200:
    names = [m["name"].split("/")[-1] for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    print([n for n in names if "flash" in n or "pro" in n][:30])
else:
    print(data)

body = {"contents": [{"parts": [{"text": "Return JSON {\"ok\": true, \"word\": \"hello\"}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
st, data, dt = call("POST", f"{BASE}/models/{model}:generateContent", body)
print("generate:", st, f"{dt:.1f}s")
if st == 200:
    print(data["candidates"][0]["content"]["parts"][0]["text"][:200])
    print("usage:", data.get("usageMetadata"))
else:
    print(data)
