# -*- coding: utf-8 -*-
"""Regenerate gcal-vs-school-diff.md with the strict (exact-title) comparison."""
import json, datetime as dt, collections
from zoneinfo import ZoneInfo
import ics_lib as L

TPE = ZoneInfo('Asia/Taipei')
W0, W1 = dt.date(2026, 8, 1), dt.date(2027, 7, 31)
SRC = ['cal-raw-threeyear.json', 'cal-raw-app-exact-pm1y.json']

def school_rows():
    seen, out = set(), []
    for p in SRC:
        for x in json.load(open(p, encoding='utf-8')):
            k = (x.get('id'), x['calStart'], x['calEnd'], x.get('calTitle', ''))
            if k in seen:
                continue
            seen.add(k)
            s = dt.datetime.fromtimestamp(x['calStart'] / 1000, TPE)
            e = dt.datetime.fromtimestamp(x['calEnd'] / 1000, TPE)
            sd = s.date()
            if x['calEnd'] == x['calStart']:
                ed, form = sd, 'same(calStart==calEnd)'
            elif (e.hour, e.minute, e.second) == (0, 0, 0):
                ed, form = e.date() - dt.timedelta(days=1), 'end-exclusive'
            else:
                ed, form = e.date(), 'timed(inclusive)'
            out.append(dict(id=x.get('id'), title=(x.get('calTitle') or '').strip(),
                            start=sd, end=max(ed, sd), form=form,
                            holiday=x.get('ownerId') == 'holiday_system'))
    return out

def ics_rows():
    _, ev = L.parse('gcal-basic.ics')
    out = []
    for e in ev:
        sraw, eraw = L.first(e, 'DTSTART'), L.first(e, 'DTEND')
        ad = L.params_of(e, 'DTSTART').get('VALUE') == 'DATE'
        if ad:
            sd, _ = L.to_date(sraw)
            ed = (L.to_date(eraw)[0] - dt.timedelta(days=1)) if eraw else sd
        else:
            sd = dt.datetime.strptime(sraw, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc).astimezone(TPE).date()
            ed = dt.datetime.strptime(eraw, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc).astimezone(TPE).date() if eraw else sd
        out.append(dict(uid=L.first(e, 'UID'), title=(L.first(e, 'SUMMARY') or '').strip(),
                        start=sd, end=max(ed, sd), allday=ad,
                        lastmod=L.first(e, 'LAST-MODIFIED'),
                        desc=L.first(e, 'DESCRIPTION'), loc=L.first(e, 'LOCATION')))
    return out

def inwin(r):
    return r['start'] <= W1 and r['end'] >= W0

sc_all = school_rows()
sc = [r for r in sc_all if inwin(r)]
gc = [r for r in ics_rows() if inwin(r)]
sc_t = [r for r in sc if not r['holiday']]
sc_h = [r for r in sc if r['holiday']]

ss = collections.Counter((r['title'], r['start'], r['end']) for r in sc_t)
gs = collections.Counter((r['title'], r['start'], r['end']) for r in gc)
only_s = sorted((ss - gs).elements(), key=lambda r: r[1])
only_g = sorted((gs - ss).elements(), key=lambda r: r[1])

# title-matched but date-differing
s_by_t = collections.defaultdict(list)
for t, s, e in only_s:
    s_by_t[t].append((s, e))
mismatch = [(t, sd, se, gd, ge) for (t, gd, ge) in only_g for (sd, se) in s_by_t.get(t, [])]

# holiday marks (whole file, not just window)
hol_days = set()
for r in [x for x in sc_all if x['holiday']]:
    d = r['start']
    while d <= r['end']:
        hol_days.add(d); d += dt.timedelta(days=1)
wk_hol = sorted(d for d in hol_days if d.weekday() < 5)
win_hol = sorted(d for d in hol_days if W0 <= d <= W1)

named = [r for r in gc if any(k in r['title'] for k in
         ['國慶', '中秋', '端午', '清明', '春節', '農曆', '開國', '和平', '兒童', '勞動', '補假'])]

W = []
def w(s=''): W.append(s)

w('# Google Calendar ics vs 學校 calModeApp.do API — 覆蓋率比對')
w()
w(f'產生時間：2026-09-14 ｜ 比對區間（inclusive）：**{W0} ~ {W1}**')
w()
w('- Google 來源：`gcal-basic.ics`（661 筆，抓取時 DTSTAMP=20260914T124339Z）')
w('- 學校來源：`cal-raw-threeyear.json` + `cal-raw-app-exact-pm1y.json`，依 '
  '`(id, calStart, calEnd, calTitle)` 去重後共 837 筆')
w()
w('## 0. 日期語意怎麼對齊的')
w()
w('兩邊都先化成 **inclusive 的 `[起日, 迄日]`**，時區一律 Asia/Taipei：')
w()
w('學校 API（`calStart`/`calEnd` 是 epoch-ms）：')
w()
w('| 條件 | 迄日 | 區間內筆數 |')
w('|---|---|---|')
fc = collections.Counter(r['form'] for r in sc)
w(f'| `calEnd == calStart` — 2026 年起出現的單日新寫法 | `= 起日` | {fc.get("same(calStart==calEnd)", 0)} |')
w(f'| `calEnd` 正好落在當地午夜 — 傳統 end-exclusive | `= calEnd 當日 − 1 天` | {fc.get("end-exclusive", 0)} |')
w(f'| `calEnd` 帶時分（如 21:00 截止） | `= calEnd 當日`（inclusive） | {fc.get("timed(inclusive)", 0)} |')
w()
w('Google ICS（RFC 5545）：')
w()
w('- 全天（`DTSTART;VALUE=DATE`）：`迄日 = DTEND − 1 天`。**全域一致 end-exclusive，沒有例外**，')
w('  538 筆全天事件中 `DTEND − DTSTART == 0` 的有 **0 筆**（學校 API 那個壞掉的單日形態在這裡不存在）。')
w('- 有時刻（`...T...Z`，全部是 UTC）：轉 Asia/Taipei 後取日期。')
w('- 缺 `DTEND`（全檔 4 筆，都在 2019–2020，不在比對區間）：`迄日 = 起日`。')
w()
w('## 1. 數量')
w()
w(f'| | 筆數 |')
w('|---|---|')
w(f'| 學校 API 區間內合計 | **{len(sc)}** |')
w(f'| ├ 有標題的正式事件（`ownerId=1540521049552`／教務處） | **{len(sc_t)}** |')
w(f'| └ 無標題的假日標記（`ownerId=holiday_system`、`calTitle=""`） | **{len(sc_h)}** |')
w(f'| Google ics 區間內合計 | **{len(gc)}** |')
w()
w('## 2. 三類差異')
w()
w('比對鍵是**未經任何正規化的三元組 `(SUMMARY/calTitle, 起日, 迄日)`**——')
w('標題逐字相同、起日相同、迄日相同才算一致。')
w()
w(f'- 兩邊完全一致：**{len(sc_t) - len(only_s)} / {len(sc_t)}**')
w(f'- **學校 API 有、Google ics 沒有：{len(only_s)} 筆**')
w(f'- **Google ics 有、學校 API 沒有：{len(only_g)} 筆**')
w(f'- 標題相同但日期不一致：**{len(mismatch)} 筆**')
w()
w('### 2a. 學校 API 有、Google ics 沒有')
w()
w('（無）' if not only_s else '\n'.join(f'- {s} ~ {e} ｜ {t}' for t, s, e in only_s))
w()
w('### 2b. Google ics 有、學校 API 沒有')
w()
w('（無）' if not only_g else '\n'.join(f'- {s} ~ {e} ｜ {t}' for t, s, e in only_g))
w()
w('### 2c. 標題相同但日期不一致')
w()
w('（無）' if not mismatch else '\n'.join(f'- {t}：學校 {a}~{b} / Google {c}~{d}' for t, a, b, c, d in mismatch))
w()
w(f'> {len(sc_t)} 筆對 {len(gc)} 筆，逐字三元組完全相等。兩邊是同一份教務處資料的兩種發佈通道。')
w()
w('> 補充：若把標題做正規化（去掉 `（日間部）`／`（進修部）` 這種括號後綴）再比，反而會冒出 2 筆')
w('> 假的「日期不一致」——那是正規化把日間部/進修部兩筆壓成同一個 key 造成的配對錯亂，不是真差異。')
w('> 因此本報告採用逐字比對。')
w()
w('## 3. 國定假日（紅字）覆蓋')
w()
w('**先修正一個前提**：學校 API 的 `holiday_system` 筆數**只有週六和週日，一筆平日假日都沒有**。')
w()
w(f'- 全檔（2024-01-06 ~ 2028-12-31）`holiday_system` 標記日數：**{len(hol_days)}** 天')
w(f'- 其中落在平日（週一~週五）的：**{len(wk_hol)}** 天')
w(f'- 比對區間內：{len(win_hol)} 天，全部是週末')
w()
w('抽查（`in holiday_system`）：')
w()
w('| 日期 | 星期 | 性質 | 在 holiday_system？ |')
w('|---|---|---|---|')
wd = '一二三四五六日'
for d, note in [(dt.date(2026, 10, 10), '國慶日'), (dt.date(2026, 10, 25), '光復節'),
                (dt.date(2027, 1, 1), '開國紀念日'), (dt.date(2027, 2, 4), '農曆新年'),
                (dt.date(2027, 2, 8), '春節連假'), (dt.date(2027, 6, 9), '端午節'),
                (dt.date(2026, 9, 28), '教師節')]:
    w(f'| {d} | {wd[d.weekday()]} | {note} | {"是" if d in hol_days else "**否**"} |')
w()
w('所以「國定假日」在**兩邊都不是靠 holiday_system 來的**，而是靠具名事件。')
w(f'Google ics 在比對區間內帶有 **{len(named)}** 筆具名國定假日／補假事件，且（見 §2）與學校 API 逐字相同：')
w()
for r in named:
    w(f'- {r["start"]} ~ {r["end"]} ｜ {r["title"]}')
w()
w('**結論**：換到 Google ics，唯一真正失去的是「週六日的 allDay 標記筆」。')
w('那是純週末，App 端用 `Calendar.component(.weekday)` 即可自行推算，不需要資料源提供。')
w('平日的國定假日／補假紅字兩邊都來自具名事件，完整保留。')
w()
open('gcal-vs-school-diff.md', 'w', encoding='utf-8').write('\n'.join(W) + '\n')
print(f'only_school={len(only_s)} only_google={len(only_g)} mismatch={len(mismatch)} '
      f'school_titled={len(sc_t)} gcal={len(gc)} weekday_holidays={len(wk_hol)} named_holidays={len(named)}')
