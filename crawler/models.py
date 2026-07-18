"""
課程目錄 (catalog) 與排課/選課計畫 資料模型 — typed v1 (Pydantic v2)。

設計與決策依據：`docs/DESIGN.md` §4.5（發佈格式/schema）、
§4.6（handoff 合約 + 階段分類 + cunum/subj 實證）、§4.7（盤點結論/來源限制）。

分層：
  canonical（git, NDJSON）→ 由爬蟲產出，型別即本檔模型
  Web v1 發佈（R2 靜態 JSON）：TermCatalog / ClassDirectory / PeriodTable / EnrollmentLatest / Manifest
  iOS/進階版：由同一 canonical 另產 SQLite（本檔不負責）
  排課→App handoff：PlanPayload（按階段分組、只帶課號+優先序）

要點（都來自實證/官方公告，勿亂改）：
  - offering_id=課號(每學期跳動、選課代碼、= cwish subj)；course_code=課程編碼(跨學期固定，同編碼可多課號=多班)
  - 節次 token 非 1..14，而是 1-9,N(中午),A-D(晚上)；weekPattern/dateRange/容量 來源**沒有**→ optional/None
  - 班級碼逐年重編、== cwish cunum(同命名空間)；研究所單一碼不分年級
  - 階段(本班/志願/加退選…)是**學生相對 + 需 live**，故**不放 catalog**，由排課/handoff 階段計算
  - 送件鐵則：依課程所屬班級分組、各帶正確 cunum（本班/授權外班碼）；cunum 取自 cwish live 清單
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2

# ============================================================== 基礎型別 / Enum

# 節次 token（固定順序，含中午 N 與晚上 A-D）。排序/grid 用 PERIOD_ORDER。
PeriodToken = Literal["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"]
PERIOD_ORDER: List[PeriodToken] = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"]

# 星期：0=日 1=一 … 6=六
Weekday = Literal[0, 1, 2, 3, 4, 5, 6]


class RequirementCategory(str, Enum):
    """修別語意（原始符號另存於 Requirement.symbol，category 須由課程標準對映、未知先 unknown）。"""
    required = "required"       # 必修
    elective = "elective"       # 選修
    general = "general"         # 通識/博雅
    program = "program"         # 學程/微學程
    unknown = "unknown"


class DivisionGroup(str, Enum):
    """學制大類（取代學長按中文檔名切分）。

    ⚠️ 偏粗、會蓋掉「進修部」語意（如在職碩專班 matric=A 被歸 graduate）。
    顯示/學分規則請改用 CourseOffering.matric_division（matric 升級的第一級欄位）。
    暫留以免破壞既有消費者，日後 deprecate。
    """
    day = "day"                 # 日間部
    extension = "extension"     # 進修部/進修學院
    graduate = "graduate"       # 研究所/碩博/EMBA/學位學程
    program = "program"         # 學程
    other = "other"


class MatricSystem(str, Enum):
    """體系（system）分類軸——與 DivisionGroup 正交，供學分規則用。

    日間部={day}；進修部系統={extension, on_job}（含進修部碩士在職專班/週末碩/EMBA）。
    日間部學生的學分加總應排除非 day 體系的課（不同體系，與選課階段分類一致）。
    """
    day = "day"                 # 日間部（含日間研究所碩博）
    extension = "extension"     # 進修部/進修學院
    on_job = "on_job"           # 在職（進修部碩士在職專班/週末碩士/EMBA）
    other = "other"             # 學程/學士後學位學程


class ClassKind(str, Enum):
    """班級種類——分類地雷：pool/virtual 班學生班級碼永不在其中（博雅/體育/英文 ~12%）。"""
    regular = "regular"         # 一般班級（年級+甲乙 或 研究所單一碼）
    pool = "pool"               # 池班級（博雅課程(一)~、體育專項、大一/大二英文…）
    virtual = "virtual"         # 佔位/向度（「請選…」指向 pool）


class WeekPattern(str, Enum):
    weekly = "weekly"           # 每週（預設；來源未提供單雙週時即此）
    odd = "odd"
    even = "even"
    unknown = "unknown"


class SelectionPhase(str, Enum):
    """選課階段/機制（官方 114-2 公告）。非 catalog 靜態屬性，由排課/handoff 計算。"""
    preselection = "preselection"               # cwish 本班直接選（本班+同系較低年級選修+授權外班）
    preference_ballot = "preference_ballot"      # cwish 志願選填分發（博雅/體育/共同英文）
    add_drop = "add_drop"                        # oads 開學加退選（創新創業/國際觀/跨校/三四年級體育/自主學習/跨域專題）
    program_registration = "program_registration"  # 獨立登記（微學程/學程/輔系/雙主修，非選課系統）
    planning_only = "planning_only"              # 僅規劃（衝堂/超學分等暫不可送）
    unknown = "unknown"                          # 無法判斷（班級資訊缺/解析失敗→不亂猜）


class SelectionSystem(str, Enum):
    cwish = "cwish"             # 期末網路預選 (aa_011_oauth)
    oads = "oads"              # 開學後加退選 (aa_030_oauth)
    freshman = "freshman"      # 新生網路選課（未驗證）
    none = "none"              # 不經選課系統（program_registration / planning_only）


class CourseAction(str, Enum):
    add = "add"
    keep = "keep"               # 只排入課表、不送件
    remove = "remove"


class WarningLevel(str, Enum):
    error = "error"             # 阻擋送出
    warning = "warning"         # 可保留、送件前再確認
    info = "info"               # 制度提醒


class WarningType(str, Enum):
    time_conflict = "time_conflict"
    credit_limit = "credit_limit"
    phase_limited = "phase_limited"
    freshman_unverified = "freshman_unverified"
    pool_course = "pool_course"          # 池課（博雅/體育/英文，志願分發）
    program_registration = "program_registration"
    unknown_rule = "unknown_rule"


# ============================================================== 建構元件

class LocalizedText(BaseModel):
    zh: str = ""
    en: Optional[str] = None


class EntityRef(BaseModel):
    """教師/教室等實體：只留 code（丟棄學長的 JSP link，避免綁死校方路徑）。"""
    code: str
    name: str = ""


class ClassRef(BaseModel):
    """開課班級 / classes.json 條目。班級碼 == cwish cunum（同命名空間、逐年重編）。"""
    code: str                                    # 班級碼（年度範圍內）
    name: str = ""
    kind: ClassKind = ClassKind.regular
    unit_code: Optional[str] = None              # 開課單位/系所碼
    grade: Optional[int] = None                  # 大學部年級；研究所通常 None（單一碼不分年級）


class Meeting(BaseModel):
    """單一上課時段。weekPattern/dateRange/教室對應＝來源未提供（§4.7）→ optional。"""
    day: Weekday
    periods: List[PeriodToken]                   # 該日節次（已排序）
    classroom_codes: List[str] = Field(default_factory=list)  # 來源無法對應到每節，多為課程層級
    week_pattern: WeekPattern = WeekPattern.weekly            # 來源無單雙週資訊→預設 weekly
    date_range: Optional[str] = None
    group: Optional[str] = None                  # 分組（實習/講課綁定）
    raw_text: Optional[str] = None


class Requirement(BaseModel):
    symbol: Optional[str] = None                 # 原始符號 ○△☆●▲★（保留）
    category: RequirementCategory = RequirementCategory.unknown
    label_zh: Optional[str] = None


class MatricDivision(BaseModel):
    """學制（matric）升為第一級的可顯示欄位：逐碼中文標籤 + 體系軸。

    code = 被選中的單一 matric 碼（多碼時依優先序裁定，見 MATRIC_LABELS 註解）；
    label = 該碼中文學制（如「進修部碩士在職專班」）；system = 體系（學分規則用）。
    無 matric 碼 → CourseOffering.matric_division 為 None。
    """
    code: str                                    # 被選中的 matric 碼
    label: str                                   # 中文學制標籤
    system: MatricSystem


# 權威 matric → (學制中文標籤, 體系)。來源＝QueryCurrPage 下拉（client.py ALL_MATRIC_CODES）。
# system 軸與 DivisionGroup 正交：進修部碩士在職專班(A) 體系 on_job，但 DivisionGroup 仍是 graduate。
MATRIC_LABELS: Dict[str, "MatricDivision"] = {
    "5": MatricDivision(code="5", label="日五專", system=MatricSystem.day),
    "6": MatricDivision(code="6", label="日二技", system=MatricSystem.day),
    "7": MatricDivision(code="7", label="日四技", system=MatricSystem.day),
    "8": MatricDivision(code="8", label="碩士", system=MatricSystem.day),
    "9": MatricDivision(code="9", label="博士", system=MatricSystem.day),
    "0": MatricDivision(code="0", label="進修學院二技", system=MatricSystem.extension),
    "4": MatricDivision(code="4", label="進修部二技", system=MatricSystem.extension),
    "F": MatricDivision(code="F", label="進修部四技", system=MatricSystem.extension),
    "A": MatricDivision(code="A", label="進修部碩士在職專班", system=MatricSystem.on_job),
    "C": MatricDivision(code="C", label="週末碩士", system=MatricSystem.on_job),
    "D": MatricDivision(code="D", label="EMBA", system=MatricSystem.on_job),
    "1": MatricDivision(code="1", label="學程", system=MatricSystem.other),
    "E": MatricDivision(code="E", label="學士後學位學程", system=MatricSystem.other),
}

# 多碼選取優先序（一門課的 matric_codes 是跨多次查詢匯集的集合）。
# 規則：以「學制具體程度」排序，把該課最主要/最具識別性的體系放在前面——
# day(5,6,7,8,9) 是主流體系優先；進修部明確標出(extension/on_job)優於泛用學程(other)。
# 同一 system 內依碼字典序取最小，確保結果【確定且可重現】。
_MATRIC_SYSTEM_PRIORITY = [
    MatricSystem.day,
    MatricSystem.extension,
    MatricSystem.on_job,
    MatricSystem.other,
]


def select_matric_division(codes) -> Optional["MatricDivision"]:
    """從一組 matric 碼裁定單一可顯示的 MatricDivision（確定性）。

    未知碼歸 system=other（不亂猜、不回退預設）；空集合 → None。
    多碼：先依 _MATRIC_SYSTEM_PRIORITY 取體系，再於該體系內取字典序最小的碼。
    """
    known = [MATRIC_LABELS[c] for c in codes if c in MATRIC_LABELS]
    unknown = sorted(c for c in codes if c and c not in MATRIC_LABELS)
    if not known:
        if unknown:
            return MatricDivision(code=unknown[0], label=unknown[0], system=MatricSystem.other)
        return None
    for system in _MATRIC_SYSTEM_PRIORITY:
        in_system = sorted((d for d in known if d.system == system), key=lambda d: d.code)
        if in_system:
            return in_system[0]
    return min(known, key=lambda d: d.code)


class Enrollment(BaseModel):
    """人數（爬取當下快照）。⚠️ 容量上限來源不提供→capacity 多為 None，僅 cwish live 可補。"""
    enrolled_count: Optional[int] = None         # 已選人數
    capacity: Optional[int] = None               # 上限（目錄端恆 None）
    withdrawn_count: Optional[int] = None         # 撤選
    observed_at: Optional[str] = None             # ISO-8601；UI 顯示陳舊警告


class Selection(BaseModel):
    """送件鍵。cunum 不放定值——實際 cunum 由 cwish live 本班/外班清單裁定（§4.6 實證）。"""
    cwish_subj: str                              # = offering_id（課號；待開窗 live 端對端驗）
    candidate_cunums: List[str] = Field(default_factory=list)  # 該課所屬班級碼（可能的 cunum 候選）


class SourceRefs(BaseModel):
    curr_code: Optional[str] = None              # Curr.jsp?format=-2&code=（課程描述/編碼）
    syllabus: List[Dict[str, str]] = Field(default_factory=list)  # [{teacher_code, snum}]


# ============================================================== 課程詳情（描述 + 大綱）

class Syllabus(BaseModel):
    """單一教師的教學大綱（ShowSyllabus.jsp；label→textarea，用標籤文字定位）。"""
    teacher_code: Optional[str] = None
    teacher_name: str = ""
    email: Optional[str] = None
    office_hours_url: Optional[str] = None
    updated_at: Optional[str] = None             # 來源「最後更新時間」
    outline: Optional[str] = None                # 課程大綱
    schedule: Optional[str] = None               # 課程進度
    assessment: Optional[str] = None             # 評量方式與標準
    materials: Optional[str] = None              # 使用教材、參考書目或其他
    consultation: Optional[str] = None           # 課程諮詢管道
    extended_resources: Optional[str] = None     # 延伸教學與資源
    sdgs: Optional[str] = None                   # 課程對應 SDGs 指標
    ai_usage: Optional[str] = None               # 課程是否導入 AI
    notes: Optional[str] = None                  # 備註
    extra: Dict[str, str] = Field(default_factory=dict)  # 來源新增的未知標籤欄（label→值）


class CourseDetail(BaseModel):
    """重文字詳情（描述 + 大綱），隨點隨取；與 catalog 分檔（catalog 保持輕、可搜尋）。"""
    model_config = ConfigDict(extra="forbid")

    term_key: str
    offering_id: str
    course_code: Optional[str] = None
    name: LocalizedText = Field(default_factory=LocalizedText)  # zh(catalog) + en(Curr)
    description: LocalizedText = Field(default_factory=LocalizedText)  # 中/英概述
    syllabi: List[Syllabus] = Field(default_factory=list)       # 逐教師
    generated_at: Optional[str] = None


# ============================================================== 核心：開課實例

class CourseOffering(BaseModel):
    """一學期一門課一班的開課實例。主鍵＝(term_key, offering_id)。"""
    model_config = ConfigDict(extra="forbid")

    term_key: str = Field(description='學期鍵，如 "115-1"')
    offering_id: str = Field(description="課號（per-term 選課代碼，跳動）；= cwish subj")
    course_code: Optional[str] = Field(default=None, description="課程編碼（跨學期固定；同編碼可多課號=多班）")

    name: LocalizedText
    credits: Optional[float] = Field(default=None, description="學分（含 0.5/0.0 佔位；加總時排除佔位課）")
    hours: Optional[float] = None
    stage: Optional[int] = None
    stage_raw: Optional[str] = None

    requirement: Requirement = Field(default_factory=Requirement)

    division_group: Optional[DivisionGroup] = None  # 偏粗、會蓋掉進修部語意；顯示請用 matric_division
    matric_codes: List[str] = Field(default_factory=list, description="該課全部學制碼集合（跨多次查詢匯集）")
    matric_division: Optional[MatricDivision] = Field(
        default=None, description="升級後的可顯示學制：中文標籤 + 體系（多碼依優先序裁定，無碼為 None）")
    unit_code: Optional[str] = None              # 開課單位/系所碼
    unit_name: Optional[str] = None
    classes: List[ClassRef] = Field(default_factory=list, description="開課班級（本班/外班分類用，含 kind）")

    teachers: List[EntityRef] = Field(default_factory=list)
    classrooms: List[EntityRef] = Field(default_factory=list)
    meetings: List[Meeting] = Field(default_factory=list)
    language: Optional[str] = Field(default=None, description="授課語言/EMI（來源第18欄，gnehs 漏抓）")

    tags: List[str] = Field(default_factory=list)        # 博雅/英文分班/遠距/英文授課…（best-effort 解析）
    notes_raw: str = ""                                  # 備註原文（會混入教室類別字，保留原文）
    is_placeholder: bool = False                         # 佔位課（notes 以「請選」開頭 或 credit=0 無師資）
    interdisciplinary: Optional[str] = None              # 跨領域欄原文（inline 微學程名）

    enrollment: Enrollment = Field(default_factory=Enrollment)
    selection: Selection
    source_refs: Optional[SourceRefs] = None
    raw_fields: Dict[str, str] = Field(default_factory=dict)  # parser debug；欄數≠24 整列入此


# ============================================================== 發佈檔 envelope

class TermInfo(BaseModel):
    key: str                                     # "115-1"
    year: int                                    # 115
    semester: Literal[1, 2, 3]                   # 1上 2下 3暑
    label: str = ""


class SourceInfo(BaseModel):
    system: str = "ntut-course-tw"
    base_url: str = "https://aps.ntut.edu.tw/course/tw/"
    crawler_name: str = "ntut-catalog-crawler"
    crawler_version: str = ""
    git_sha: Optional[str] = None


class Freshness(BaseModel):
    catalog_crawled_at: Optional[str] = None
    enrollment_observed_at: Optional[str] = None


class TermCatalog(BaseModel):
    """catalog.json：Web v1 主檔（前端建索引）。重文字(描述/課綱)拆 course/{id}.json 隨點隨取。"""
    schema_version: int = SCHEMA_VERSION
    term: TermInfo
    generated_at: Optional[str] = None
    source: SourceInfo = Field(default_factory=SourceInfo)
    freshness: Freshness = Field(default_factory=Freshness)
    courses: List[CourseOffering] = Field(default_factory=list)


class PeriodRef(BaseModel):
    """periods.json 條目：節次 token ↔ 牆鐘時間（Asia/Taipei），grid/ICS 用。"""
    token: PeriodToken
    order: int
    start_hm: str                                # "08:10"
    end_hm: str                                  # "09:00"
    label: str                                   # 顯示用（１ ２ … Ｎ … Ａ）


class PeriodTable(BaseModel):
    schema_version: int = SCHEMA_VERSION
    timezone: str = "Asia/Taipei"
    periods: List[PeriodRef] = Field(default_factory=list)


class ClassDirectory(BaseModel):
    """classes.json：逐學期；Web 身分選擇器（系所/年級/班）+ 本班判斷；班級碼可預填 cwish cunum。"""
    schema_version: int = SCHEMA_VERSION
    term_key: str
    classes: List[ClassRef] = Field(default_factory=list)


class EnrollmentLatest(BaseModel):
    """enrollment.json：volatile overlay；選課季可高頻更新，疊在已快取 catalog 上。"""
    schema_version: int = SCHEMA_VERSION
    term_key: str
    observed_at: Optional[str] = None
    counts: Dict[str, Enrollment] = Field(default_factory=dict)  # offering_id -> Enrollment


MProgramCategory = Literal["基礎", "核心", "總整", "進階", "應用"]


class MicroProgramCourse(BaseModel):
    """微學程課程標準列（Cprog -4，matric=H）。"""
    course_code: str
    name_zh: str = ""
    credits: Optional[float] = None
    category: Optional[MProgramCategory] = None   # notes 正規化；映不出 → None
    category_raw: Optional[str] = None            # notes 原文保底
    emi: bool = False                             # notes 內 e 標記（Task 2 實證）


class MicroProgram(BaseModel):
    """微學程：SearchMProgram。offering_ids = 該學程該學期開課的課號。"""
    code: str
    name: str
    offering_ids: List[str] = Field(default_factory=list)
    courses: List[MicroProgramCourse] = Field(default_factory=list)
    rules_text: Optional[str] = None              # 「相關規定」原文，保留換行，不解析


class MicroProgramDirectory(BaseModel):
    """mprograms.json：逐學期微學程清單 + 各學程開課課號。"""
    schema_version: int = SCHEMA_VERSION
    term_key: str
    programs: List[MicroProgram] = Field(default_factory=list)


class StandardCourse(BaseModel):
    """課程標準單列（Cprog format=-4）：某入學年/學制/系所的應修課程。"""
    study_year: Optional[int] = None             # 建議修讀學年
    study_sem: Optional[int] = None              # 建議修讀學期
    requirement: Requirement = Field(default_factory=Requirement)  # 修別（符號→類別）
    course_code: Optional[str] = None            # 課程編碼（與 catalog course_code 對接）
    name_zh: str = ""
    credits: Optional[float] = None
    hours: Optional[float] = None
    stage: Optional[str] = None
    group_id: Optional[str] = None               # 群組編號（應修學分群）
    notes: str = ""


class ProgramStandard(BaseModel):
    """某入學年×學制×系所的課程標準/畢業標準（Cprog 葉節點）。"""
    entry_year: int
    matric: str                                  # 學制碼
    division: str                                # 系所/學程碼
    title: str = ""                              # 頁面標題（如「四技 通識中心【博雅課程－自然】」）
    courses: List[StandardCourse] = Field(default_factory=list)


class StandardDirectory(BaseModel):
    """standards/{entry_year}.json：某入學年所有 program 的課程標準。"""
    schema_version: int = SCHEMA_VERSION
    entry_year: int
    programs: List[ProgramStandard] = Field(default_factory=list)


class ManifestEntry(BaseModel):
    url: str
    sha256: str
    size: int
    content_encoding: Optional[str] = None       # gzip/br
    schema_version: int = SCHEMA_VERSION


class ManifestTerm(BaseModel):
    catalog: ManifestEntry
    enrollment: Optional[ManifestEntry] = None
    classes: Optional[ManifestEntry] = None
    periods: Optional[ManifestEntry] = None
    mprograms: Optional[ManifestEntry] = None     # 微學程（逐學期）
    dataset_version: Optional[str] = None         # payload 帶此值；App 過舊→提示重驗


class Manifest(BaseModel):
    """manifest.json：client 先抓（極小），比對 sha256 決定要不要重抓。"""
    schema_version: int = SCHEMA_VERSION
    generated_at: Optional[str] = None
    min_app_version: Optional[str] = None
    terms: Dict[str, ManifestTerm] = Field(default_factory=dict)  # term_key -> ManifestTerm


# ============================================================== 排課 → App handoff

class StudentContext(BaseModel):
    """供 App 重新檢查階段/限制；不含帳密。class_code 用『碼』非名稱（= cwish cunum）。"""
    unit_code: Optional[str] = None
    grade: Optional[int] = None
    class_code: Optional[str] = None             # 班級碼（年度範圍；= cwish cunum）
    class_name: Optional[str] = None             # 顯示用
    is_freshman: bool = False


class PlanCourse(BaseModel):
    offering_id: str                             # 課號（App 用自身 catalog 還原細節）
    action: CourseAction = CourseAction.add
    priority: Optional[int] = None               # preselection 內排序＝cwish subj 陣列順序（前者先選入）
    cwish_cunum: Optional[str] = None            # 送件 cunum（本班/授權外班碼）；App 由 live 裁定後填
    reason: Optional[str] = None                 # external_class / cross_department / time_conflict …


class PlanGroup(BaseModel):
    """已按階段分組——App 不需重猜送件順序；送件鐵則：同一 cwish 群組仍須依 cwish_cunum 再分批。"""
    phase: SelectionPhase
    system: SelectionSystem = SelectionSystem.none
    courses: List[PlanCourse] = Field(default_factory=list)


class PlanWarning(BaseModel):
    level: WarningLevel
    type: WarningType
    offering_id: Optional[str] = None
    message: str
    related_offering_ids: List[str] = Field(default_factory=list)


class PlanPayload(BaseModel):
    """Web 匯出 → Universal Link/URL Scheme 導入 App。只帶課號+學期+優先序+階段分組。"""
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    school: str = "ntut"
    semester: str                                # "115-1"
    dataset_version: Optional[str] = None        # 對應 catalog 版本；App 過舊→提示重驗
    source: str = "ntutbox-planner-web"
    created_at: Optional[str] = None
    student_context: Optional[StudentContext] = None
    plans: List[PlanGroup] = Field(default_factory=list)
    warnings: List[PlanWarning] = Field(default_factory=list)
