import sys, os, json
from pathlib import Path

REPO = Path("/Users/poterpan/Documents/Coding/NTUT/NTUT_Tools")
env_path = REPO / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(REPO))
from ntut.core.auth import NTUTAuthenticator

OUT = Path("/private/tmp/claude-503/-Users-poterpan-Documents-Coding-SwiftUI-NTUTBox/8306211c-b5b3-4571-928f-17673fd57fa3/scratchpad")

auth = NTUTAuthenticator()
r = auth.login_app(os.environ["NTUT_USERNAME"], os.environ["NTUT_PASSWORD"])
print("LOGIN success=", r.success, "msg=", r.message)
if not r.success:
    sys.exit(1)

URL = "https://app.ntut.edu.tw/calModeApp.do"

def probe(tag, data):
    headers = auth.get_headers("app.ntut.edu.tw", {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    ok, resp, msg = auth.make_request("POST", URL, headers=headers, data=data)
    if not ok:
        print(f"[{tag}] REQUEST FAILED: {msg}")
        return None
    path = OUT / f"cal-raw-{tag}.json"
    path.write_bytes(resp.content)
    ct = resp.headers.get("Content-Type", "")
    n = None
    try:
        j = resp.json()
        n = len(j) if isinstance(j, list) else "not-list"
    except Exception as e:
        n = f"JSONERR {e}"
    print(f"[{tag}] params={data} HTTP={resp.status_code} ct={ct} bytes={len(resp.content)} items={n} -> {path.name}")
    return resp

import sys as _s
cases = json.loads(_s.argv[1])
for tag, data in cases:
    probe(tag, data)
