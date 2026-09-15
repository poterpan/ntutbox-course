import sys, os, json, datetime
from pathlib import Path
REPO = Path("/Users/poterpan/Documents/Coding/NTUT/NTUT_Tools")
for line in (REPO/".env").read_text().splitlines():
    line=line.strip()
    if line and not line.startswith("#") and "=" in line:
        k,v=line.split("=",1); os.environ[k.strip()]=v.strip()
sys.path.insert(0,str(REPO))
from ntut.core.auth import NTUTAuthenticator
OUT=Path(".").resolve()
auth=NTUTAuthenticator()
r=auth.login_app(os.environ["NTUT_USERNAME"], os.environ["NTUT_PASSWORD"])
print("LOGIN success=", r.success)
if not r.success: sys.exit(1)
h=auth.get_headers("app.ntut.edu.tw", {"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"})
ok,resp,msg=auth.make_request("POST","https://app.ntut.edu.tw/calModeApp.do",headers=h,
    data={"startDate":"2027/01/01","endDate":"2027/01/31"})
print("HTTP",resp.status_code,"bytes",len(resp.content),"ct",resp.headers.get("Content-Type"))
(OUT/"cal-live-61722-jan2027.json").write_bytes(resp.content)
j=resp.json()
hit=[e for e in j if e.get("id")==61722]
print("該區間筆數:",len(j),"| id=61722 命中:",len(hit))
TZ=datetime.timezone(datetime.timedelta(hours=8))
for e in hit:
    print("\n===== 原始物件（逐欄，未經處理）=====")
    print(json.dumps(e,ensure_ascii=False,indent=2,sort_keys=False))
    print("\n===== 欄位清單與型別 =====")
    for k,v in e.items():
        print(f"  {k:18} {type(v).__name__:6} {repr(v)[:70]}")
    print("\n===== 時間戳換算（Asia/Taipei）=====")
    for k in ("calStart","calEnd"):
        if isinstance(e.get(k),int):
            print(f"  {k} = {e[k]} -> {datetime.datetime.fromtimestamp(e[k]/1000,TZ)}")
    print("  calEnd - calStart =", e["calEnd"]-e["calStart"], "毫秒")
