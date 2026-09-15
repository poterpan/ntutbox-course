import sys, os, json, datetime
from pathlib import Path
REPO = Path("/Users/poterpan/Documents/Coding/NTUT/NTUT_Tools")
for line in (REPO/".env").read_text().splitlines():
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); os.environ[k.strip()]=v.strip()
sys.path.insert(0,str(REPO))
from ntut.core.auth import NTUTAuthenticator
TZ=datetime.timezone(datetime.timedelta(hours=8))
D=lambda ms: datetime.datetime.fromtimestamp(ms/1000,TZ).strftime("%m/%d %H:%M")
auth=NTUTAuthenticator(); r=auth.login_app(os.environ["NTUT_USERNAME"],os.environ["NTUT_PASSWORD"])
assert r.success
def hdr(post=False):
    h=auth.get_headers("app.ntut.edu.tw",{"Accept":"application/json"})
    if post: h["Content-Type"]="application/x-www-form-urlencoded"
    return h
ok,resp,_=auth.make_request("POST","https://app.ntut.edu.tw/calModeApp.do",headers=hdr(True),
    data={"startDate":"2026/12/20","endDate":"2027/02/28"})
lst=[e for e in resp.json() if e.get("calTitle") and e.get("id")]
print(f"列表取得 {len(lst)} 筆具名事件\n")
print(f"{'id':>6}  {'標題':22} {'list:start→end':24} {'show:start→end':24} {'show-list(end)':>14}")
print("-"*100)
for e in sorted(lst,key=lambda x:x["calStart"]):
    ok2,r2,_=auth.make_request("GET","https://app.ntut.edu.tw/calShow.do",headers=hdr(),params={"id":str(e["id"])})
    try: c=r2.json()["cal"]
    except Exception: print(f"{e['id']:>6}  {e['calTitle'][:20]:22} <calShow 解析失敗>"); continue
    dl=e["calEnd"]-e["calStart"]; ds=c["calEnd"]-c["calStart"]
    diff=(c["calEnd"]-e["calEnd"])/86400000
    flag=" ←零長度" if dl==0 else ""
    print(f"{e['id']:>6}  {e['calTitle'][:20]:22} {D(e['calStart'])+' → '+D(e['calEnd']):24} {D(c['calStart'])+' → '+D(c['calEnd']):24} {diff:>+10.0f} 天{flag}")
