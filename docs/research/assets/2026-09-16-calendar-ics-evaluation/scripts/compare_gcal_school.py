# -*- coding: utf-8 -*-
"""Compare NTUT school calendar API (calModeApp.do raw JSON) against the
public Google Calendar ics feed, over a common window.

Date alignment
--------------
School API: calStart / calEnd are epoch-ms. Converted to Asia/Taipei.
  * end_date = start_date                       when calEnd == calStart (the 2026+ "inclusive single day" form)
  * end_date = taipei(calEnd).date() - 1 day    when calEnd lands exactly on local midnight (classic end-exclusive)
  * end_date = taipei(calEnd).date()            otherwise (timed event, e.g. 21:00 deadline -> inclusive)
Google ICS: DTSTART/DTEND per RFC5545.
  * all-day (VALUE=DATE): end_date = DTEND - 1 day   (end-exclusive, always)
  * timed (UTC):          end_date = taipei(DTEND).date()
  * no DTEND:             end_date = start_date
Both sides therefore end up as an INCLUSIVE [start_date, end_date] span.
"""
import json, sys, datetime as dt, collections, re, unicodedata
from zoneinfo import ZoneInfo
import ics_lib as L

TPE = ZoneInfo('Asia/Taipei')
WIN_START = dt.date(2026, 8, 1)
WIN_END   = dt.date(2027, 7, 31)

def ms_to_tpe(ms):
    return dt.datetime.fromtimestamp(ms / 1000, TPE)

def load_school(paths):
    seen, rows = set(), []
    for p in paths:
        for x in json.load(open(p, encoding='utf-8')):
            s = ms_to_tpe(x['calStart'])
            e = ms_to_tpe(x['calEnd'])
            sd = s.date()
            if x['calEnd'] == x['calStart']:
                ed, form = sd, 'same'                       # 2026+ inclusive single-day
            elif (e.hour, e.minute, e.second) == (0, 0, 0):
                ed, form = e.date() - dt.timedelta(days=1), 'exclusive'
            else:
                ed, form = e.date(), 'timed'
            if ed < sd:
                ed = sd
            is_hol = x.get('ownerId') == 'holiday_system'
            key = (x.get('id'), x['calStart'], x['calEnd'], x.get('calTitle', ''))
            if key in seen:
                continue
            seen.add(key)
            rows.append(dict(id=x.get('id'), title=(x.get('calTitle') or '').strip(),
                             start=sd, end=ed, form=form, holiday=is_hol,
                             allDay=x.get('allDay'), content=x.get('calContent', ''),
                             raw_start=x['calStart'], raw_end=x['calEnd']))
    return rows

def load_ics(path):
    _, ev = L.parse(path)
    rows = []
    for e in ev:
        sraw = L.first(e, 'DTSTART')
        eraw = L.first(e, 'DTEND')
        allday = L.params_of(e, 'DTSTART').get('VALUE') == 'DATE'
        sd, _ = L.to_date(sraw)
        if allday:
            if eraw:
                ed, _ = L.to_date(eraw)
                ed = ed - dt.timedelta(days=1)
            else:
                ed = sd
        else:
            # UTC timestamps -> convert to Taipei
            sdt = dt.datetime.strptime(sraw, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc).astimezone(TPE)
            sd = sdt.date()
            if eraw:
                edt = dt.datetime.strptime(eraw, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc).astimezone(TPE)
                ed = edt.date()
            else:
                ed = sd
        if ed < sd:
            ed = sd
        rows.append(dict(uid=L.first(e, 'UID'), title=(L.first(e, 'SUMMARY') or '').strip(),
                         start=sd, end=ed, allday=allday,
                         desc=L.first(e, 'DESCRIPTION'), loc=L.first(e, 'LOCATION'),
                         lastmod=L.first(e, 'LAST-MODIFIED')))
    return rows

def overlaps(r):
    return r['start'] <= WIN_END and r['end'] >= WIN_START

def norm(t):
    """Normalise a title for matching: fullwidth->halfwidth, drop spaces and
    all bracketed parentheticals, unify punctuation."""
    t = unicodedata.normalize('NFKC', t)
    t = re.sub(r'[（(\[【][^）)\]】]*[）)\]】]', '', t)
    t = re.sub(r'[\s　,，、。.:：;；~～\-－_/｜|]+', '', t)
    return t

def main():
    school = [r for r in load_school(['cal-raw-threeyear.json', 'cal-raw-app-exact-pm1y.json']) if overlaps(r)]
    gcal   = [r for r in load_ics('gcal-basic.ics') if overlaps(r)]
    s_hol  = [r for r in school if r['holiday']]
    s_tit  = [r for r in school if not r['holiday']]

    out = []
    W = out.append
    W('# Google Calendar ics vs 學校 calModeApp.do API — 覆蓋率比對')
    W('')
    W(f'比對區間（inclusive）：{WIN_START} ~ {WIN_END}')
    W(f'資料來源：`cal-raw-threeyear.json` + `cal-raw-app-exact-pm1y.json`（去重後）vs `gcal-basic.ics`')
    W('')
    W('## 0. 日期語意對齊方式')
    W('')
    W(__doc__.split('Date alignment')[1].split('----')[1].strip())
    W('')
    form_ct = collections.Counter(r['form'] for r in school)
    W(f'區間內學校 API 的三種 calEnd 形態：{dict(form_ct)}')
    W('')
    W('## 1. 數量')
    W('')
    W(f'- 學校 API 區間內總筆數：**{len(school)}**')
    W(f'  - 有標題的正式事件（ownerId=1540521049552）：**{len(s_tit)}**')
    W(f'  - 無標題的國定假日標記（ownerId=holiday_system，calTitle 為空字串）：**{len(s_hol)}**')
    W(f'- Google ics 區間內總筆數：**{len(gcal)}**')
    W('')

    # ---- match titled school events against gcal ----
    g_by_norm = collections.defaultdict(list)
    for g in gcal:
        g_by_norm[norm(g['title'])].append(g)
    used = set()
    exact, shifted, missing = [], [], []
    for s in s_tit:
        cands = g_by_norm.get(norm(s['title']), [])
        best, bestd = None, None
        for i, g in enumerate(cands):
            if id(g) in used:
                continue
            d = abs((g['start'] - s['start']).days)
            if bestd is None or d < bestd:
                best, bestd = g, d
        if best is None:
            missing.append(s)
        elif bestd == 0 and best['end'] == s['end']:
            used.add(id(best)); exact.append((s, best))
        elif bestd <= 7:
            used.add(id(best)); shifted.append((s, best, bestd))
        else:
            missing.append(s)
    extra = [g for g in gcal if id(g) not in used]

    W('## 2. 三類差異（只比對「有標題」的正式事件）')
    W('')
    W(f'- 兩邊都有、日期完全一致：**{len(exact)}**')
    W(f'- 兩邊都有、標題相同但起訖日不同：**{len(shifted)}**')
    W(f'- 學校 API 有、Google ics 沒有：**{len(missing)}** ← 換源會漏掉的')
    W(f'- Google ics 有、學校 API 沒有：**{len(extra)}**')
    W('')

    W('### 2a. 學校 API 有、Google ics 沒有（逐筆）')
    W('')
    if not missing:
        W('（無）')
    else:
        W('| # | 起 | 迄 | 標題 | id | calEnd 形態 |')
        W('|---|---|---|---|---|---|')
        for i, s in enumerate(sorted(missing, key=lambda r: r['start']), 1):
            W(f"| {i} | {s['start']} | {s['end']} | {s['title']} | {s['id']} | {s['form']} |")
    W('')

    W('### 2b. Google ics 有、學校 API 沒有（逐筆）')
    W('')
    if not extra:
        W('（無）')
    else:
        W('| # | 起 | 迄 | 標題 | 全天 |')
        W('|---|---|---|---|---|')
        for i, g in enumerate(sorted(extra, key=lambda r: r['start']), 1):
            W(f"| {i} | {g['start']} | {g['end']} | {g['title']} | {'Y' if g['allday'] else 'N'} |")
    W('')

    W('### 2c. 標題相同但日期不一致（逐筆）')
    W('')
    if not shifted:
        W('（無）')
    else:
        W('| # | 學校起~迄 | Google起~迄 | 標題 | 差(天) |')
        W('|---|---|---|---|---|')
        for i, (s, g, d) in enumerate(sorted(shifted, key=lambda x: x[0]['start']), 1):
            W(f"| {i} | {s['start']}~{s['end']} | {g['start']}~{g['end']} | {s['title']} | {d} |")
    W('')

    # ---- holiday coverage ----
    hol_dates = set()
    for r in s_hol:
        d = r['start']
        while d <= r['end']:
            if WIN_START <= d <= WIN_END:
                hol_dates.add(d)
            d += dt.timedelta(days=1)
    g_dates = set()
    for g in gcal:
        d = g['start']
        while d <= g['end']:
            g_dates.add(d); d += dt.timedelta(days=1)
    weekend = {d for d in hol_dates if d.weekday() >= 5}
    weekday_hol = sorted(hol_dates - weekend)
    covered = [d for d in weekday_hol if d in g_dates]
    W('## 3. 國定假日（紅字）覆蓋')
    W('')
    W(f'- 學校 API 的 holiday_system 標記日數：**{len(hol_dates)}** 天')
    W(f'  - 其中週六／週日：{len(weekend)} 天')
    W(f'  - 其中平日補假／國定假日：**{len(weekday_hol)}** 天')
    W(f'- 這些平日假日中，Google ics 「有任何事件覆蓋到該日」的：{len(covered)} / {len(weekday_hol)}')
    W('')
    W('| 平日假日 | 星期 | Google ics 當天事件 |')
    W('|---|---|---|')
    wd = '一二三四五六日'
    for d in weekday_hol:
        hits = [g['title'] for g in gcal if g['start'] <= d <= g['end']]
        W(f"| {d} | {wd[d.weekday()]} | {'; '.join(hits) if hits else '**（無）**'} |")
    W('')
    W('> Google ics 完全沒有「無標題的假日標記」這種資料——它只有具名事件。')
    W('> 週末的紅字本來就可以由 App 端自行推算；但**平日補假／國定假日必須另找來源**。')
    W('')

    json.dump(dict(school_total=len(school), school_titled=len(s_tit), school_holiday=len(s_hol),
                   gcal_total=len(gcal), exact=len(exact), shifted=len(shifted),
                   missing=len(missing), extra=len(extra),
                   holiday_days=len(hol_dates), weekday_holidays=len(weekday_hol)),
              open('gcal-vs-school-summary.json', 'w'), indent=2, default=str)
    open('gcal-vs-school-diff.md', 'w', encoding='utf-8').write('\n'.join(out))
    print('\n'.join(out[:60]))
    print('...')
    print('WROTE gcal-vs-school-diff.md')

main()
