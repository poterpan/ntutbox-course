"""課程進度（syllabus.schedule 自由文字）→ 結構化逐週進度。契約一／二。

核心解析移植自 POC（/Users/poterpan/.../ntut-course-progress-poc，320 行、無第三方依賴），
**邏輯逐字保留**，好讓回歸數字可重現；在其上加三條新規則（a/b/c）。

保守原則：只輸出有明確證據的對應，**不臆造教師沒寫的內容**。看起來像週次但沒有佐證的
（例如沒有日期欄的純編號清單）一律拒絕——誤把章節當週次是使用者看得見的錯誤，
比空白嚴重得多。

POC 實測記錄的 6 條陷阱（每一條都對應下面的具體防線）：
  1. `第19週` 沒有數字邊界會被錯讀成第 9 週     → ARABIC_NUMBER 的 (?<!\\d)(?!\\d)
  2. `第4週後的進度需自行規劃` 是備註不是 topic → CHINESE_SINGLE_RE 的 (?!...後|前|開始)
  3. `一週／二週` 是「要花一到兩週」不是第 1／2 週 → _is_unprefixed_chinese_duration
  4. `Week 2: ... may move to week 3` 後半是敘述  → 每行只取第一個 marker
  5. 中英各寫一遍會產生同週不同語言候選          → 規則 (a)，沒有可靠配對時不硬合併
  6. `第4週～第8週` 兩端都有「週」               → CHINESE_RANGE_RE 整段吃掉
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from models import AcademicTerm, TermWeek, WeeklyProgress, WeeklyProgressWeek
from ntut_catalog.ics import TAIPEI

PARSER_VERSION = "progress/1.0.0"
DEFAULT_WEEK_COUNT = 18

CHINESE_NUMBER = "十八|十七|十六|十五|十四|十三|十二|十一|十|九|八|七|六|五|四|三|二|一"
ARABIC_NUMBER = r"(?<!\d)(?:0?[1-9]|1[0-8])(?!\d)"          # 陷阱 1：數字邊界
NUMBER = rf"(?:{CHINESE_NUMBER}|{ARABIC_NUMBER})"
RANGE_SEPARATOR = r"(?:~|～|-|－|–|—|至|到)"
LIST_SEPARATOR = r"(?:,|，|、|/)"

CHINESE_LIST_RE = re.compile(
    rf"(?:第\s*)?(?P<items>{NUMBER}(?:\s*{LIST_SEPARATOR}\s*{NUMBER})+)\s*[週周]")
CHINESE_RANGE_RE = re.compile(                              # 陷阱 6：整段吃掉
    rf"(?:第\s*)?(?P<start>{NUMBER})\s*[週周]?\s*{RANGE_SEPARATOR}\s*"
    rf"(?:第\s*)?(?P<end>{NUMBER})\s*[:：]?\s*[週周]")
CHINESE_SINGLE_RE = re.compile(                             # 陷阱 2：排除「第N週後/前/開始」
    rf"(?:第\s*)?(?P<week>{NUMBER})\s*[週周](?!\s*(?:後|前|以後|以前|開始))")
ENGLISH_WEEK_RE = re.compile(
    rf"(?i)\b(?:weeks?|wks?|wk|w)\.?\s*(?P<start>{ARABIC_NUMBER})"
    rf"(?:\s*(?:~|–|-|to)\s*(?:(?:weeks?|wks?|wk|w)\.?\s*)?(?P<end>{ARABIC_NUMBER}))?\b")

ANY_CHINESE_WEEK_RE = re.compile(
    r"(?:第\s*)?(?P<start>\d{1,3})\s*(?:(?:~|～|-|－|–|—|至|到)\s*"
    r"(?:第\s*)?(?P<end>\d{1,3})\s*)?[:：]?\s*[週周]")
ANY_ENGLISH_WEEK_RE = re.compile(
    r"(?i)\b(?:weeks?|wks?|wk|w)\.?\s*(?P<start>\d{1,3})"
    r"(?:\s*(?:~|–|-|to)\s*(?:(?:weeks?|wks?|wk|w)\.?\s*)?(?P<end>\d{1,3}))?\b")

CHINESE_TO_INT = {c: i + 1 for i, c in enumerate(
    "一 二 三 四 五 六 七 八 九 十".split())}
CHINESE_TO_INT.update({f"十{c}": 10 + i + 1 for i, c in enumerate("一 二 三 四 五 六 七 八".split())})

_UNPARSEABLE_MARKERS = ("tba", "t.b.a", "待定", "依課堂狀況調整", "另行公布", "視情況")


@dataclass(frozen=True)
class WeekSegment:
    start_week: int
    end_week: int
    topic: str
    source_line: str
    line_number: int
    marker: str
    marker_kind: Literal["single", "range", "list"]

    @property
    def span(self) -> int:
        return self.end_week - self.start_week + 1


@dataclass(frozen=True)
class ParseIssue:
    code: str
    message: str
    source_line: str
    line_number: int


@dataclass
class ParseResult:
    segments: List[WeekSegment] = field(default_factory=list)
    issues: List[ParseIssue] = field(default_factory=list)


@dataclass(frozen=True)
class _Marker:
    start: int
    end: int
    weeks: Tuple[int, ...]
    text: str
    kind: Literal["single", "range", "list"]


def _number(value: str) -> int:
    return CHINESE_TO_INT.get(value, int(value) if value.isascii() else 0)


def _is_unprefixed_chinese_duration(marker: str) -> bool:
    """陷阱 3：`一週／二週` 是「這單元要花一到兩週」，不是第 1／2 週。

    中文數字沒有「第」就保守拒絕。阿拉伯數字形式（`1-4週`）仍接受——那是來源的主流表格格式。
    這是刻意用 recall 換 precision。
    """
    stripped = marker.lstrip()
    return not stripped.startswith("第") and bool(re.match(CHINESE_NUMBER, stripped))


def _candidate_markers(line: str) -> List[_Marker]:
    candidates: List[_Marker] = []
    for match in CHINESE_LIST_RE.finditer(line):
        if _is_unprefixed_chinese_duration(match.group()):
            continue
        items = re.split(r"\s*[,，、/]\s*", match.group("items"))
        candidates.append(_Marker(match.start(), match.end(),
                                  tuple(_number(i) for i in items), match.group(), "list"))
    for match in CHINESE_RANGE_RE.finditer(line):
        if _is_unprefixed_chinese_duration(match.group()):
            continue
        candidates.append(_Marker(match.start(), match.end(),
                                  (_number(match.group("start")), _number(match.group("end"))),
                                  match.group(), "range"))
    for match in CHINESE_SINGLE_RE.finditer(line):
        if _is_unprefixed_chinese_duration(match.group()):
            continue
        candidates.append(_Marker(match.start(), match.end(),
                                  (_number(match.group("week")),), match.group(), "single"))
    for match in ENGLISH_WEEK_RE.finditer(line):
        start = int(match.group("start"))
        end = int(match.group("end")) if match.group("end") else None
        candidates.append(_Marker(match.start(), match.end(),
                                  (start, end) if end is not None else (start,),
                                  match.group(), "range" if end is not None else "single"))

    # list/range 的文字也會命中 single。取最長者，只丟掉字元重疊的候選。
    selected: List[_Marker] = []
    for cand in sorted(candidates, key=lambda m: (m.start, -(m.end - m.start))):
        if any(cand.start < m.end and m.start < cand.end for m in selected):
            continue
        selected.append(cand)
    # 陷阱 4：課程進度壓倒性地一列一行。解析同一行後面的 marker 會把
    # 「may move to week 3 ... scheduled in week 1」這種敘述誤讀成新的一列。
    return sorted(selected, key=lambda m: m.start)[:1]


def _clean_topic(value: str) -> str:
    value = re.sub(r"^[\s\t:：;；,，、.。\[\]【】\-–—]+", "", value)
    value = re.sub(r"[\s\t:：;；,，、.。\[\]【】\-–—]+$", "", value).strip()
    if value in {"(", ")", "（", "）"}:
        return ""
    if (value.startswith("(") and value.endswith(")")) or \
       (value.startswith("（") and value.endswith("）")):
        value = value[1:-1]
    else:
        value = re.sub(r"[（(]\s*$", "", value)      # 週次常寫成括號註記：主題（第1, 2週）
        value = re.sub(r"^\s*[）)]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _topic_for_marker(line: str, markers: List[_Marker], index: int) -> str:
    marker = markers[index]
    next_start = markers[index + 1].start if index + 1 < len(markers) else len(line)
    after = _clean_topic(line[marker.end:next_start])
    if after:
        return after
    previous_end = markers[index - 1].end if index else 0
    return _clean_topic(line[previous_end:marker.start])


def _out_of_range_issues(line: str, line_number: int, week_count: int) -> List[ParseIssue]:
    issues: List[ParseIssue] = []
    for pattern in (ANY_CHINESE_WEEK_RE, ANY_ENGLISH_WEEK_RE):
        for match in pattern.finditer(line):
            values = [int(match.group("start"))]
            if match.group("end"):
                values.append(int(match.group("end")))
            invalid = [v for v in values if not 1 <= v <= week_count]
            if invalid:
                issues.append(ParseIssue("week_out_of_range",
                                         f"week must be within 1...{week_count}: {invalid}",
                                         line, line_number))
    return issues


# 規則 (e)：週次標記獨占一行、主題在下一行。來源是表格的儲存格換行變成文字換行，
# 週次其實明確寫著——這不是「猜」，是我們原本只在同一行找主題而漏抓。
_MARKER_ONLY_RE = re.compile(
    r"^\s*(?:第\s*\d{1,2}\s*[週周]|(?i:w|wk|week)\s*\.?\s*\d{1,2})\s*[:：.、]?\s*$")
_LEADING_DATE_RE = re.compile(r"^\s*\(?\d{1,2}\s*(?:/|月)\s*\d{1,2}\s*日?\)?\s*")


def _merge_marker_only_lines(text: str) -> List[Tuple[int, str]]:
    """把「只有週次標記的行」與下一行併成一行。回傳 [(原行號, 文字)]。

    只在下一行**本身不含任何週次 marker** 時才併——否則 `第1週 ⏎ 第2週 導論` 會被誤併。
    併進來的主題若以日期開頭（`09/10 課程內容簡介`）把日期剝掉，那是欄位不是主題。
    """
    lines = [(i, l.strip()) for i, l in enumerate(text.splitlines(), 1)]
    lines = [(i, l) for i, l in lines if l]
    out: List[Tuple[int, str]] = []
    skip = False
    for idx, (line_number, line) in enumerate(lines):
        if skip:
            skip = False
            continue
        if _MARKER_ONLY_RE.match(line) and idx + 1 < len(lines):
            nxt = lines[idx + 1][1]
            if not _candidate_markers(nxt):
                out.append((line_number, f"{line} {_LEADING_DATE_RE.sub('', nxt)}"))
                skip = True
                continue
        out.append((line_number, line))
    return out


def parse_schedule(text: str, week_count: int = DEFAULT_WEEK_COUNT) -> ParseResult:
    """抽出有明確週次 marker 的段落。不臆造缺漏的結構。"""
    result = ParseResult()
    seen: set = set()
    for line_number, line in _merge_marker_only_lines(text):
        if not line:
            continue
        result.issues.extend(_out_of_range_issues(line, line_number, week_count))
        markers = _candidate_markers(line)
        for index, marker in enumerate(markers):
            topic = _topic_for_marker(line, markers, index)
            if marker.kind == "range":
                start_week, end_week = marker.weeks
                if start_week > end_week:
                    result.issues.append(ParseIssue(
                        "reversed_range", f"range starts after it ends: {start_week}...{end_week}",
                        line, line_number))
                    continue
                week_ranges = [(start_week, end_week)]
            elif marker.kind == "list":
                week_ranges = [(w, w) for w in marker.weeks]
            else:
                week_ranges = [(marker.weeks[0], marker.weeks[0])]
            for start_week, end_week in week_ranges:
                key = (start_week, end_week, topic.casefold(), line_number)
                if key in seen:
                    continue
                seen.add(key)
                result.segments.append(WeekSegment(start_week, end_week, topic, line,
                                                   line_number, marker.text, marker.kind))
    result.segments.sort(key=lambda s: (s.start_week, s.end_week, s.line_number))
    return result


def _normalized_topic(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def resolve_week(result: ParseResult, week: int,
                 week_count: int = DEFAULT_WEEK_COUNT) -> Dict:
    """解析單一週，較窄的段落優先於大標題。

    同寬度但不同 topic 的多個候選維持 ambiguous，**不任選一個**。
    """
    if not 1 <= week <= week_count:
        raise ValueError(f"week must be within 1...{week_count}")
    candidates = [s for s in result.segments if s.start_week <= week <= s.end_week and s.topic]
    if not candidates:
        return {"status": "missing", "week": week, "candidates": []}
    narrowest_span = min(s.span for s in candidates)
    by_topic: Dict[str, WeekSegment] = {}
    for s in (c for c in candidates if c.span == narrowest_span):
        by_topic.setdefault(_normalized_topic(s.topic), s)
    resolved = list(by_topic.values())
    return {"status": "resolved" if len(resolved) == 1 else "ambiguous",
            "week": week, "candidates": resolved}


# ====================================================== 規則 (a)：雙語配對

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_BILINGUAL_MIN_CJK = 0.3        # CJK 那筆的 CJK 佔比下限
_BILINGUAL_MIN_LATIN = 0.6      # 拉丁那筆的字母佔比下限


def _ratio(pattern: re.Pattern, text: str) -> float:
    body = re.sub(r"\s", "", text)
    return len(pattern.findall(body)) / len(body) if body else 0.0


def pair_bilingual(segments: Sequence[WeekSegment]) -> Optional[List[WeekSegment]]:
    """規則 (a)：把「中英各寫一遍」的兩個候選判為語言變體，合併成同一週的兩個 topic。

    **恰有 2 個**候選、一個 CJK 佔比 ≥ 0.3、另一個 CJK 佔比 = 0 且拉丁字母佔比 ≥ 0.6
    → 判為語言變體，回傳 [CJK, Latin]（CJK 在前），**status 不降級**。

    拒絕（回傳 None，該週維持 ambiguous）：候選 ≥ 3、兩者同語系、任一 topic 為空。
    陷阱 5 說的就是這件事：沒有可靠語言配對時**不得硬合併字串**。

    依據：使用者實測第 2 門課中英各寫一遍，18 週全部 ambiguous，這條就能全數救回。
    """
    if len(segments) != 2 or not all(s.topic for s in segments):
        return None
    ranked = []
    for s in segments:
        cjk, latin = _ratio(_CJK_RE, s.topic), _ratio(_LATIN_RE, s.topic)
        ranked.append((s, cjk, latin))
    cjk_side = [r for r in ranked if r[1] >= _BILINGUAL_MIN_CJK]
    latin_side = [r for r in ranked if r[1] == 0.0 and r[2] >= _BILINGUAL_MIN_LATIN]
    if len(cjk_side) != 1 or len(latin_side) != 1 or cjk_side[0][0] is latin_side[0][0]:
        return None
    return [cjk_side[0][0], latin_side[0][0]]


# ====================================================== 規則 (b)：編號＋日期表

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:/|月)\s*(\d{1,2})\s*日?(?!\d)")
_COLUMN_SPLIT_RE = re.compile(r"\t+| {2,}")
_MIN_TABLE_ROWS = 12            # 列數下限（建議值）；太短的表沒有足夠證據


def _parse_md(token: str) -> Optional[Tuple[int, int]]:
    m = _DATE_RE.search(token)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    return (month, day) if 1 <= month <= 12 and 1 <= day <= 31 else None


def parse_numbered_date_table(text: str, base_year: int,
                              week_count: int = DEFAULT_WEEK_COUNT
                              ) -> Optional[List[Tuple[int, str, str]]]:
    """規則 (b)：首欄是 1,2,3... 且某一欄是每列差恰好 7 天的日期 → 首欄即週次。

    **首欄 1..N 與「每列差 7 天」互相證明，資料自己驗證自己**，所以自動接受。

    拒絕（回傳 None）：
      - 任一相鄰對不是 7 天（調課／放假會出現 14 天，這時不要猜）
      - 首欄序列不從 1 開始、非單調 +1、或有缺口
      - 列數 < 12
    年份補齊：以該學期首週的年份起算，月份回捲（12 → 1）時 +1 年。
    """
    rows: List[Tuple[int, Tuple[int, int], str]] = []
    for raw in text.splitlines():
        cols = [c.strip() for c in _COLUMN_SPLIT_RE.split(raw.strip()) if c.strip()]
        if len(cols) < 2 or not re.fullmatch(r"\d{1,2}", cols[0]):
            continue
        date_idx = next((i for i in range(1, len(cols)) if _parse_md(cols[i])), None)
        if date_idx is None:
            continue
        topic = _clean_topic(" ".join(c for i, c in enumerate(cols) if i not in (0, date_idx)))
        rows.append((int(cols[0]), _parse_md(cols[date_idx]), topic))

    if len(rows) < _MIN_TABLE_ROWS or [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        return None

    year, dates = base_year, []
    prev_month = None
    for _, (month, day) in ((r[0], r[1]) for r in rows):
        if prev_month is not None and month < prev_month:
            year += 1
        prev_month = month
        try:
            dates.append(dt.date(year, month, day))
        except ValueError:
            return None
    if any((b - a).days != 7 for a, b in zip(dates, dates[1:])):
        return None
    return [(r[0], d.isoformat(), r[2]) for r, d in zip(rows, dates) if r[0] <= week_count]


# ====================================================== 規則 (c)：純日期清單

_ANY_WEEK_MARKER_RE = re.compile(r"(?i)[週周]|\bweeks?\b")


def parse_date_list(text: str, term_weeks: Sequence[TermWeek]
                    ) -> Optional[List[Tuple[int, str, str]]]:
    """規則 (c)：行內只有日期、沒有週次 marker → 用該學期 weeks[] 把日期映射到週次。

    **需要契約三先就位。** 拒絕（回傳 None）：映射結果有重複週次，或任一日期落在學期外
    → **整份拒絕**。日期表格式通常一致，局部失敗代表判讀方向錯了，不做部分接受。
    """
    if not term_weeks:
        return None
    spans = [(dt.date.fromisoformat(w.start), dt.date.fromisoformat(w.end), w.number)
             for w in term_weeks]
    base_year = spans[0][0].year
    out: List[Tuple[int, str, str]] = []
    seen_weeks: set = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _ANY_WEEK_MARKER_RE.search(line):
            return None                       # 有週次 marker → 不是這條規則的場景
        md = _parse_md(line)
        if md is None:
            continue
        month, day = md
        # 學期跨年時月份會回捲；兩個候選年份取落在學期區間內的那個
        candidates = [dt.date(y, month, day) for y in (base_year, base_year + 1)
                      if _valid_date(y, month, day)]
        hit = next(((d, n) for d in candidates for s, e, n in spans if s <= d <= e), None)
        if hit is None:
            return None                       # 落在學期外 → 整份拒絕
        date, week = hit
        if week in seen_weeks:
            return None                       # 重複週次 → 整份拒絕
        seen_weeks.add(week)
        topic = _clean_topic(_DATE_RE.sub("", line))
        out.append((week, date.isoformat(), topic))
    return out or None


def _valid_date(year: int, month: int, day: int) -> bool:
    try:
        dt.date(year, month, day)
        return True
    except ValueError:
        return False


# ====================================================== 規則 (d)：行事曆錨點編號清單

_NUMBERED_ROW_RE = re.compile(r"^\s*\(?(\d{1,2})\s*[.)、,\t ]\s*(.+)$")
_MIDTERM_RE = re.compile(r"(?i)期中(?:考|測驗)|midterm")
_FINAL_RE = re.compile(r"(?i)期末(?:考|測驗)|final\s*exam")


def _week_of(term: AcademicTerm, date_iso: str) -> Optional[int]:
    return next((w.number for w in term.weeks if w.start <= date_iso <= w.end), None)


def parse_anchored_numbered_list(text: str, term: AcademicTerm,
                                 week_count: int = DEFAULT_WEEK_COUNT
                                 ) -> Optional[List[Tuple[int, str, str]]]:
    """規則 (d)：純編號清單，但**期中考／期末考剛好落在行事曆對應的週次** → 首欄即週次。

    我們原本明確拒絕沒有日期佐證的純編號清單（「14 項對不上 18 週，很可能是章節」）。
    這條開一個**有條件**的例外，條件是行事曆提供了一個原本沒有的獨立證人：

        9    Midterm Exam      ← 行事曆說 115-1 期中考在第 9 週
        15   期末考             ← 行事曆說期末考在第 15 週

    首欄如果真是章節編號，第 9 列寫「期中考」是巧合；但行事曆來自完全獨立的來源
    （校方公告），對得上就構成雙證人——與規則 (b)「首欄 1..N 與每列差 7 天互相證明」
    同一個精神。

    拒絕：
      - 序列不從 1 開始、非單調 +1、有缺口，或列數 < 12、> week_count
      - 期中／期末**沒有落在行事曆對應的那一列**（不給 ±1 容差；容差一放，佐證就垮了）
    """
    rows: Dict[int, str] = {}
    for raw in text.splitlines():
        match = _NUMBERED_ROW_RE.match(raw.strip())
        if match:
            rows[int(match.group(1))] = match.group(2).strip()
    if not (_MIN_TABLE_ROWS <= len(rows) <= week_count):
        return None
    if sorted(rows) != list(range(1, len(rows) + 1)):
        return None

    # **只用期中考當錨點，而且要求剛好對上。** 這是量出來的，不是挑的：
    # 115-1 全量掃過，期中考落在行事曆對應週的偏移分布在 0 有一個銳利的峰（132 筆），
    # 尾巴很小；期末考則完全不可靠——峰值在 +1（82 筆）與 +3（53 筆）、剛好只有 16 筆，
    # 因為期末考期 12/18-12/24 橫跨第 15、16 週，而且很多教師把「期末」寫在最後一列
    # （第 18 列，彈性學習週）。拿不可靠的錨點當證據，等於把誤判引進來。
    expected = _week_of(term, term.midterm.start)
    if expected is None:
        return None
    where = [week for week, text in rows.items() if _MIDTERM_RE.search(text)]
    if where != [expected]:
        # 沒寫期中考 → 沒有證據；寫了但不在對應那一列 → 首欄很可能是「第幾次上課」
        # 或章節編號，不是週次。兩種都拒絕。
        return None
    return [(week, "", _clean_topic(rows[week])) for week in sorted(rows)]

# ====================================================== 契約一：組出 WeeklyProgress

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_unparseable_text(schedule: Optional[str]) -> bool:
    if not schedule or not schedule.strip():
        return True
    body = schedule.strip().casefold()
    return len(body) < 4 or any(m in body for m in _UNPARSEABLE_MARKERS)


def _unparsed(schedule: Optional[str], notes: List[str], now: str) -> WeeklyProgress:
    """unparsed 也要寫出來（帶 parser_version），App 才能誠實顯示「教師未提供」
    而不是「載入中」。"""
    return WeeklyProgress(status="unparsed", weeks=[], notes=notes,
                          parser_version=PARSER_VERSION, parsed_at=now,
                          source_schedule_sha256=_sha256(schedule or ""))


def build_weekly_progress(
    schedule: Optional[str],
    week_count: int = DEFAULT_WEEK_COUNT,
    term: Optional[AcademicTerm] = None,
    now: Optional[str] = None,
) -> WeeklyProgress:
    """`schedule` 自由文字 → 三態的結構化逐週進度。

    順序：先跑 marker parser（POC 的保守路徑）；它一週都解不出來時，才試規則 (b)(c)——
    那兩條處理的是「整張表都沒有週次 marker」的格式，與 marker 路徑互斥。

    ambiguous 的呈現（**不另設 candidates 欄位**）：能被規則 (a) 判定的合併成同一週的兩個
    topic、status 不降級；其餘**不寫進 weeks**，在 notes 留一行、該週視為 missing、
    status 降 partial。取捨：App 的版位是一行「本週：主題」，多候選在那裡沒有正確的
    呈現方式；把不確定性丟給 client 只會讓每個 consumer 各自發明取捨、而且發明得不一致。
    """
    now = now or dt.datetime.now(TAIPEI).isoformat(timespec="seconds")
    if _is_unparseable_text(schedule):
        return _unparsed(schedule, [], now)

    notes: List[str] = []
    weeks: List[WeeklyProgressWeek] = []
    ambiguous_weeks = 0

    result = parse_schedule(schedule, week_count)
    resolved_any = any(resolve_week(result, w, week_count)["status"] != "missing"
                       for w in range(1, week_count + 1))

    if resolved_any:
        for week in range(1, week_count + 1):
            state = resolve_week(result, week, week_count)
            if state["status"] == "missing":
                continue
            candidates: List[WeekSegment] = state["candidates"]
            if state["status"] == "ambiguous":
                paired = pair_bilingual(candidates)
                if paired is None:
                    ambiguous_weeks += 1
                    notes.append(f"第 {week} 週有 {len(candidates)} 個無法判定的候選，已略過")
                    continue
                candidates = paired
            weeks.append(WeeklyProgressWeek(
                week=week,
                topics=[c.topic for c in candidates],
                source_lines=list(dict.fromkeys(c.source_line for c in candidates)),
            ))
    else:
        rows = None
        if term is not None and term.weeks:
            base_year = dt.date.fromisoformat(term.weeks[0].start).year
            rows = parse_numbered_date_table(schedule, base_year, week_count)
            if rows is None:
                rows = parse_date_list(schedule, term.weeks)
            if rows is None:
                rows = parse_anchored_numbered_list(schedule, term, week_count)
        if not rows:
            return _unparsed(schedule, notes, now)
        for week, _date, topic in rows:
            if topic:
                weeks.append(WeeklyProgressWeek(week=week, topics=[topic], source_lines=[]))

    if not weeks:
        return _unparsed(schedule, notes, now)
    status = "resolved" if len(weeks) == week_count and not ambiguous_weeks else "partial"
    return WeeklyProgress(status=status, weeks=weeks, notes=notes,
                          parser_version=PARSER_VERSION, parsed_at=now,
                          source_schedule_sha256=_sha256(schedule))


def attach_weekly_progress(syllabi, term: Optional[AcademicTerm] = None,
                           now: Optional[str] = None) -> None:
    """就地把 weekly_progress 掛到每份 syllabus 上。

    **每份各自一份，不合併、不投票、不取第一份**——115-1 有 112 個開課實例的不同教師
    寫了互相衝突的進度，挑哪一位是 consumer 的事。
    """
    week_count = len(term.weeks) if term is not None and term.weeks else DEFAULT_WEEK_COUNT
    now = now or dt.datetime.now(TAIPEI).isoformat(timespec="seconds")
    for syllabus in syllabi:
        syllabus.weekly_progress = build_weekly_progress(
            syllabus.schedule, week_count, term, now)


def progress_report(details, term_key: str, generated_at: str,
                    had_term_weeks: bool) -> Dict:
    """三態統計，寫進 data/reports/{term}/weekly-progress.json，用來長期追蹤精度。

    **gold set 不阻擋上線**——上線靠三態誠實揭露 ＋ parser_version 逐步提升。
    """
    status_counts = {"resolved": 0, "partial": 0, "unparsed": 0}
    cells_with_topic = 0
    syllabi_total = 0
    week_count = DEFAULT_WEEK_COUNT
    for detail in details:
        for syllabus in detail.syllabi:
            wp = syllabus.weekly_progress
            if wp is None:
                continue
            syllabi_total += 1
            status_counts[wp.status] += 1
            cells_with_topic += len(wp.weeks)
    cells_total = syllabi_total * week_count
    return {
        "schema_version": 1,
        "term_key": term_key,
        "generated_at": generated_at,
        "parser_version": PARSER_VERSION,
        "term_weeks_available": had_term_weeks,   # False → 規則 (b)(c) 未啟用
        "syllabi": syllabi_total,
        "status_counts": status_counts,
        "week_cells": {
            "total": cells_total,
            "with_topic": cells_with_topic,
            "rate": round(cells_with_topic / cells_total, 6) if cells_total else 0.0,
        },
    }
