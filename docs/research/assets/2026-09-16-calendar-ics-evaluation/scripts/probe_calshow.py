import sys, os, json, re
from pathlib import Path
REPO = Path("/Users/poterpan/Documents/Coding/NTUT/NTUT_Tools")
for line in (REPO/".env").read_text().splitlines():
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); os.environ[k.strip()]=v.strip()
sys.path.insert(0,str(REPO))
from ntut.core.auth import NTUTAuthenticator
auth=NTUTAuthenticator()
r=auth.login_app(os.environ["NTUT_USERNAME"], os.environ["NTUT_PASSWORD"])
print("LOGIN success=", r.success)
if not r.success: sys.exit(1)
URL="https://app.ntut.edu.tw/calShow.do"
def show(tag, method, **kw):
    h=auth.get_headers("app.ntut.edu.tw", {"Accept":"application/json, text/html"})
    if method=="POST": h["Content-Type"]="application/x-www-form-urlencoded"
    ok,resp,msg=auth.make_request(method,URL,headers=h,**kw)
    if not ok:
        print(f"[{tag}] FAILED: {msg}"); return
    body=resp.content
    Path(f"calshow-{tag}.raw").write_bytes(body)
    ct=resp.headers.get("Content-Type","")
    print(f"\n[{tag}] {method} {kw} -> HTTP {resp.status_code} ct={ct} bytes={len(body)}")
    txt=body.decode("utf-8","replace")
    try:
        print("  JSON:", json.dumps(resp.json(),ensure_ascii=False)[:1200])
    except Exception:
        t=re.sub(r"<script.*?</script>|<style.*?</style>","",txt,flags=re.S|re.I)
        t=re.sub(r"<[^>]+>"," ",t); t=re.sub(r"\s+"," ",t).strip()
        print("  TEXT:", t[:600] if t else "(空)")
show("get-id","GET",params={"id":"61722"})
show("post-id","POST",data={"id":"61722"})
show("get-calId","GET",params={"calId":"61722"})
show("get-bare","GET")
