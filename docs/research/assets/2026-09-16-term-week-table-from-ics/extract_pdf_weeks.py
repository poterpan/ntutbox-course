"""從北科官方行事曆 PDF 抽出週次表，產生 pdf-week-tables-111-115.json。

一次性的證據萃取腳本，不進發布管線。發布端（ics-only）用產出的 JSON 當回歸
fixture，不需要再碰 PDF。

用法：python3 extract_pdf_weeks.py <pdf 目錄> > pdf-week-tables-111-115.json
來源 PDF：https://oaa.ntut.edu.tw/var/file/8/1008/img/2878/{YYY}Calendar.pdf
（列表頁 https://oaa.ntut.edu.tw/p/412-1008-12781.php?Lang=zh-tw 當日只掛 112-115，
111 是直接猜 URL 取得；sha256 見 source-pdf-sha256.txt）

作法：不寫死欄位座標。每頁先從「週」「次」表頭定出週次欄 x，從星期列的「日」
定出週日欄 x，再把週次標籤與週日數字按 y 配對。日期用暴力錨定——在起始月 ±45 天
內找一個週日，使整串 day-of-month 全部吻合；吻合即自我驗證，不吻合就沒有輸出。
"""
import sys, re, json, datetime as dt
import fitz  # PyMuPDF

CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,
      '十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'十八':18,'十九':19,'二十':20}


def _geometry(words):
    """回傳 (週次欄 x, 週日欄 x)。以表頭文字定位，勿寫死座標。"""
    xw = min(w[0] for w in words if w[4] == '週')
    header_y = min(w[1] for w in words if w[4] == '次')
    xs = min(w[0] for w in words if w[4] == '日' and abs(w[1] - header_y) < 3)
    return xw, xs


def extract_term(page, roc_year, term):
    words = page.get_text("words")
    xw, xs = _geometry(words)
    labels = sorted((w[1], w[4]) for w in words
                    if xw - 9 <= w[0] <= xw + 6 and (w[4] in CN or w[4] in ('準備', '結束')))
    sundays = sorted((w[1], int(w[4])) for w in words
                     if abs(w[0] - xs) < 7 and re.fullmatch(r'\d{1,2}', w[4]))
    rows = []
    for sy, day in sundays:
        near = min(labels, key=lambda L: abs(L[0] - sy)) if labels else None
        rows.append((near[1] if near and abs(near[0] - sy) < 13 else None, day))

    start_month = 8 if term == 1 else 2
    start_year = roc_year + 1911 if term == 1 else roc_year + 1912
    base = dt.date(start_year, start_month, 1)
    anchor = None
    for offset in range(-45, 46):
        cand = base + dt.timedelta(days=offset)
        if cand.weekday() != 6:          # 只錨在週日
            continue
        cur, ok = cand, True
        for _, day in rows:
            if cur.day != day:
                ok = False
                break
            cur += dt.timedelta(days=7)
        if ok:
            anchor = cand
            break
    if anchor is None:
        raise ValueError(f"{roc_year}-{term}: 無法錨定日期序列")

    seq, cur = [], anchor
    for label, _ in rows:
        seq.append((label, cur))
        cur += dt.timedelta(days=7)
    numbered = [(CN[l], d) for l, d in seq if l in CN]
    prep = [d for l, d in seq if l == '準備']
    if [n for n, _ in numbered] != list(range(1, len(numbered) + 1)):
        raise ValueError(f"{roc_year}-{term}: 週次編號不連續")
    return {
        'rows': len(rows),
        'week_count': len(numbered),
        'nums': [n for n, _ in numbered],
        'prep': str(prep[0]) if prep else None,   # 月界時標籤落在後半列，可能抓不到
        'week1': str(numbered[0][1]),
        'weeks': [[n, str(d)] for n, d in numbered],
    }


def main(pdf_dir):
    out = {}
    for roc_year in (111, 112, 113, 114, 115):
        doc = fitz.open(f"{pdf_dir}/{roc_year}.pdf")
        for page_no, term in ((0, 1), (1, 2)):
            out[f"{roc_year}-{term}"] = extract_term(doc[page_no], roc_year, term)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
