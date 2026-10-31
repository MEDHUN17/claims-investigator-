import json, time, urllib.request, urllib.error
from pathlib import Path
env = dict(l.split("=",1) for l in Path("backend/.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
key = env["GEMINI_API_KEY"].strip()
BASE = "https://generativelanguage.googleapis.com/v1beta"
body = {"contents":[{"parts":[{"text":"Return JSON {\"ok\": true}"}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0}}
for m in ["gemini-3.8-flash","gemini-3.7-flash","gemini-3.6-flash","gemini-3.5-flash","gemini-flash-latest","gemini-3-flash-preview","gemini-2.5-flash"]:
    req = urllib.request.Request(f"{BASE}/models/{m}:generateContent", method="POST", data=json.dumps(body).encode(), headers={"x-goog-api-key":key,"Content-Type":"application/json"})
    t=time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d=json.loads(r.read()); print(m, r.status, f"{time.time()-t:.1f}s", d["candidates"][0]["content"]["parts"][0]["text"].strip()[:30], d.get("usageMetadata",{}).get("totalTokenCount"))
    except urllib.error.HTTPError as e:
        print(m, e.code, f"{time.time()-t:.1f}s", e.read().decode()[:90].replace("\n"," "))
    except Exception as e:
        print(m, "ERR", repr(e)[:80])
