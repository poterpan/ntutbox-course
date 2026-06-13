# Infra 資料管線 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。Steps 用 `- [ ]`。
> ⚠️ 本 repo 慣例：實作到**上線前**為止——**不**建 public GitHub repo、**不**建 R2 bucket、**不** push、**不**設 secrets、**不**跑 live publish。這些等使用者最後本地確認後再做。
> 依據：`docs/superpowers/specs/2026-06-13-infra-data-pipeline-design.md`。

**Goal:** 把 P0 爬蟲變成自動化管線的「程式碼 + 設定」全部就緒：structural catalog + enrollment snapshot + build-v1 + 自動偵測學期 + publish.py（quality gate/原子/dry-run）+ crawl.yml + SETUP.md，並把既有 11 學期離線遷移成新格式、canonical 移到 orphan `data` branch。

**Architecture:** canonical（git `data` branch）= 完整單一來源（catalog.ndjson 結構 + classes.json + enrollment/{date}.ndjson 時序）；v1（R2、ephemeral）由 `build_v1` 從 canonical 完整重建；GitHub Actions cron 自動偵測當前學期 → 爬 → commit canonical → build-v1 → quality gate → wrangler 推 R2。

**Tech Stack:** Python 3.12 · pydantic≥2 · httpx · bs4/html5lib · pytest · wrangler(CLI) · GitHub Actions

---

## 檔案結構

| 檔案 | 責任 | 動作 |
|---|---|---|
| `crawler/ntut_catalog/client.py` | + `detect_current_term()` 讀 QueryCurrPage | 改 |
| `crawler/ntut_catalog/artifacts.py` | structural catalog 輸出（非 mutate）、`write_canonical`、`write_enrollment_snapshot`、`build_v1`、`write_manifest`(調整) | 大改 |
| `crawler/ntut_catalog/orchestrator.py` | crawl_term 不變（已非 mutate 驗證）；確認 enrollment 物件不共用 | 微調 |
| `crawler/ntut_catalog/cli.py` | skip-check 改 canonical；`current-term` 子命令；crawl 改走 write_canonical + build_v1 | 改 |
| `crawler/ntut_catalog/migrate.py` | 既有 11 學期離線遷移（catalog 去 volatile/timestamp、classes 落 canonical、seed snapshot） | 新增 |
| `infra/publish.py` | build-v1 → quality gate → wrangler 原子發佈 + dry-run | 新增 |
| `infra/r2-cors.json` | R2 CORS policy | 新增 |
| `infra/SETUP.md` | Cloudflare/GH 手動設定步驟 | 新增 |
| `infra/redline_scan.py` | canonical 資料紅線掃描（學號/cookie/token/HTML 錯誤頁） | 新增 |
| `.github/workflows/crawl.yml` | cron + dispatch workflow | 新增 |
| `.gitignore` | main 擋整個 `data/` | 改 |

**節次表 `periods.py`、解析層 `parse_*`、`normalize.py`、`classes_builder.py`、`models.py` 不動**（已穩定）。

---

## Phase A — Schema/Crawler 改造

### Task A1: `detect_current_term()` + `current-term` CLI

**Files:** Modify `crawler/ntut_catalog/client.py`；Modify `crawler/ntut_catalog/cli.py`；Test `crawler/tests/test_client.py`、`crawler/tests/test_cli.py`

- [ ] **Step 1: 失敗測試**（用既有 fixture `querycurrpage_tw.html`，其 year selected=115）

```python
# tests/test_client.py 追加
from ntut_catalog.client import parse_current_term

def test_parse_current_term_from_querycurrpage():
    html = (FIXTURES / "querycurrpage_tw.html").read_text(encoding="utf-8")
    assert parse_current_term(html) == "115-1"  # year option selected=115, sem 預設上學期=1

def test_parse_current_term_sem_lower():
    html = '<select name="year"><option>114</option><option selected>115</option></select>' \
           '<select name="sem"><option>上學期</option><option selected>下學期</option></select>'
    assert parse_current_term(html) == "115-2"
```

- [ ] **Step 2: 跑測試確認 fail**：`cd crawler && .venv/bin/pytest tests/test_client.py -k current_term -v` → ImportError。

- [ ] **Step 3: 實作 `parse_current_term` + `detect_current_term`**（client.py）

```python
import re
from bs4 import BeautifulSoup

def parse_current_term(html: str) -> str:
    """讀 QueryCurrPage 下拉的 selected year/sem → 'YYY-S'（比照 gnehs fetchYearSem）。"""
    soup = BeautifulSoup(html, "html5lib")
    def _selected(name: str) -> str:
        sel = soup.find("select", attrs={"name": name})
        if sel is None:
            raise ValueError(f"select[name={name}] not found")
        opt = sel.find("option", selected=True) or sel.find("option")
        return opt.get_text(strip=True)
    year = _selected("year")
    sem_text = _selected("sem")
    sem = 1 if "上" in sem_text else 2
    if not re.fullmatch(r"\d{3}", year):
        raise ValueError(f"unexpected year: {year!r}")
    return f"{year}-{sem}"

# CatalogClient 方法：
    def query_curr_page(self) -> str:
        return self._request("GET", "QueryCurrPage.jsp")

def detect_current_term(client: "CatalogClient") -> str:
    return parse_current_term(client.query_curr_page())
```

- [ ] **Step 4: CLI `current-term` 子命令**（cli.py，印 term 到 stdout 供 workflow 擷取）

```python
# 在 sub.add_parser 區塊加：
    sub.add_parser("current-term", help="偵測當前學期並印出（如 115-1）")
# main() dispatch：
    if args.command == "current-term":
        client = CatalogClient()
        try:
            print(detect_current_term(client))
        finally:
            client.close()
        return 0
```

- [ ] **Step 5: 跑測試**：`.venv/bin/pytest tests/test_client.py -k current_term -v` → PASS。
- [ ] **Step 6: live smoke**：`.venv/bin/python -m ntut_catalog current-term` → 印出 `115-1`（確認真站台）。
- [ ] **Step 7: commit**：`git add -A && git commit -m "feat(crawler): detect current term from QueryCurrPage"`

### Task A2: structural catalog 輸出（非 mutate、去 timestamp、去 raw_fields 人數）

**Files:** Modify `crawler/ntut_catalog/artifacts.py`；Test `crawler/tests/test_artifacts.py`(新增)

`Enrollment` volatile 欄位＝`enrolled_count/withdrawn_count/observed_at`（capacity 恆 None）。raw_fields 中 volatile keys＝`enrolled/withdrawn`（normalize.py 寫入的鍵）。

- [ ] **Step 1: 失敗測試**

```python
# tests/test_artifacts.py（新檔）
from models import CourseOffering, Enrollment, LocalizedText, Selection, TermCatalog, TermInfo
from ntut_catalog.artifacts import structural_course, structural_catalog

def _course():
    return CourseOffering(
        term_key="115-1", offering_id="300001", name=LocalizedText(zh="x"),
        selection=Selection(cwish_subj="300001"),
        enrollment=Enrollment(enrolled_count=73, withdrawn_count=2, observed_at="2026-06-13T00:00:00+08:00"),
        raw_fields={"enrolled": "73", "withdrawn": "2", "matric_codes": "7"},
    )

def test_structural_course_strips_volatile_without_mutating():
    c = _course()
    s = structural_course(c)
    assert s.enrollment.enrolled_count is None and s.enrollment.observed_at is None
    assert "enrolled" not in s.raw_fields and "withdrawn" not in s.raw_fields
    assert s.raw_fields["matric_codes"] == "7"          # 結構性 raw 保留
    # 原物件不被改動（overlay 來源安全）
    assert c.enrollment.enrolled_count == 73 and c.raw_fields["enrolled"] == "73"

def test_structural_catalog_strips_timestamps():
    cat = TermCatalog(term=TermInfo(key="115-1", year=115, semester=1),
                      generated_at="2026-06-13T00:00:00+08:00",
                      freshness={"catalog_crawled_at": "x", "enrollment_observed_at": "y"},
                      courses=[_course()])
    s = structural_catalog(cat)
    assert s.generated_at is None
    assert s.freshness.catalog_crawled_at is None and s.freshness.enrollment_observed_at is None
    assert s.courses[0].enrollment.enrolled_count is None
    assert cat.generated_at == "2026-06-13T00:00:00+08:00"   # 原物件不變
```

- [ ] **Step 2: 跑測試 fail**：`.venv/bin/pytest tests/test_artifacts.py -v` → ImportError。
- [ ] **Step 3: 實作**（artifacts.py）

```python
from models import Enrollment, Freshness
_VOLATILE_RAW_KEYS = ("enrolled", "withdrawn")

def structural_course(c):
    s = c.model_copy(deep=True)
    s.enrollment = Enrollment()  # 全 None
    s.raw_fields = {k: v for k, v in s.raw_fields.items() if k not in _VOLATILE_RAW_KEYS}
    return s

def structural_catalog(cat):
    s = cat.model_copy(deep=True)
    s.generated_at = None
    s.freshness = Freshness()  # 全 None
    s.courses = [structural_course(c) for c in s.courses]
    return s
```

- [ ] **Step 4: 跑測試 PASS**：`.venv/bin/pytest tests/test_artifacts.py -v`。
- [ ] **Step 5: commit**：`git commit -am "feat(crawler): structural catalog helpers (strip volatile, non-mutating)"`

### Task A3: `write_canonical` + `write_enrollment_snapshot`

**Files:** Modify `crawler/ntut_catalog/artifacts.py`；Test `crawler/tests/test_artifacts.py`

canonical 佈局：`{out}/canonical/{term}/catalog.ndjson`（structural）、`classes.json`、`enrollment/{date}.ndjson`。snapshot 行＝`{offering_id, enrolled_count, withdrawn_count, observed_at}`（用 EnrollmentLatest.counts 來源）。

- [ ] **Step 1: 失敗測試**

```python
import json
from ntut_catalog.artifacts import write_canonical, write_enrollment_snapshot
# 用 test_orchestrator 的 FakeClient result 或自建小 TermResult

def test_write_canonical_structural(tmp_path, sample_result):  # sample_result fixture 見下
    write_canonical(sample_result, tmp_path)
    nd = (tmp_path/"canonical"/"115-1"/"catalog.ndjson").read_text().strip().splitlines()
    first = json.loads(nd[0])
    assert first["enrollment"]["enrolled_count"] is None       # 結構檔不含數字
    assert (tmp_path/"canonical"/"115-1"/"classes.json").exists()

def test_write_enrollment_snapshot(tmp_path, sample_result):
    write_enrollment_snapshot(sample_result, tmp_path, "2026-06-13")
    snap = (tmp_path/"canonical"/"115-1"/"enrollment"/"2026-06-13.ndjson").read_text().strip().splitlines()
    rec = json.loads(snap[0])
    assert set(rec) == {"offering_id", "enrolled_count", "withdrawn_count", "observed_at"}
```

`sample_result` fixture：`conftest.py` 用既有 FakeClient（test_orchestrator）跑 `crawl_term` 得 TermResult。把 FakeClient 移到 `tests/conftest.py` 共用。

- [ ] **Step 2: fail** → **Step 3: 實作**

```python
def write_canonical(result, out_dir):
    term = result.catalog.term.key
    d = out_dir / "canonical" / term
    d.mkdir(parents=True, exist_ok=True)
    with (d/"catalog.ndjson").open("w", encoding="utf-8") as f:
        for c in result.catalog.courses:
            f.write(structural_course(c).model_dump_json(exclude_none=False) + "\n")
    (d/"classes.json").write_text(result.classes.model_dump_json(), encoding="utf-8")

def write_enrollment_snapshot(result, out_dir, date):
    d = out_dir / "canonical" / result.catalog.term.key / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    with (d/f"{date}.ndjson").open("w", encoding="utf-8") as f:
        for oid, e in result.enrollment.counts.items():
            f.write(json.dumps({"offering_id": oid, "enrolled_count": e.enrolled_count,
                                "withdrawn_count": e.withdrawn_count, "observed_at": e.observed_at},
                               ensure_ascii=False) + "\n")
```

- [ ] **Step 4: PASS** → **Step 5: commit** `feat(crawler): write canonical (structural catalog + classes + enrollment snapshot)`

### Task A4: `build_v1`（canonical → 完整 v1 + manifest）

**Files:** Modify `crawler/ntut_catalog/artifacts.py`；Test `crawler/tests/test_artifacts.py`

從 canonical 重建 v1：catalog.json（structural envelope，generated_at=None）、classes.json（copy）、periods.json（build_period_table）、enrollment.json（讀**最新**日期 snapshot → EnrollmentLatest）。再 write_manifest。

- [ ] **Step 1: 失敗測試**

```python
from models import TermCatalog, ClassDirectory, PeriodTable, EnrollmentLatest, Manifest
from ntut_catalog.artifacts import write_canonical, write_enrollment_snapshot, build_v1

def test_build_v1_from_canonical(tmp_path, sample_result):
    write_canonical(sample_result, tmp_path)
    write_enrollment_snapshot(sample_result, tmp_path, "2026-06-13")
    build_v1(tmp_path, "2026-06-13T01:00:00+08:00")
    t = tmp_path/"v1"/"terms"/"115-1"
    cat = TermCatalog.model_validate_json((t/"catalog.json").read_text())
    assert cat.generated_at is None and cat.courses[0].enrollment.enrolled_count is None
    enr = EnrollmentLatest.model_validate_json((t/"enrollment.json").read_text())
    assert enr.counts                                  # 最新 snapshot 還原數字
    ClassDirectory.model_validate_json((t/"classes.json").read_text())
    PeriodTable.model_validate_json((t/"periods.json").read_text())
    man = Manifest.model_validate_json((tmp_path/"v1"/"manifest.json").read_text())
    assert "115-1" in man.terms

def test_build_v1_covers_all_terms(tmp_path, sample_result):
    # 兩個學期 canonical → manifest 兩個都在（回歸 Codex manifest 不完整）
    write_canonical(sample_result, tmp_path); write_enrollment_snapshot(sample_result, tmp_path, "2026-06-13")
    r2 = sample_result; r2.catalog.term.key = "114-2"  # 簡化：另存一份
    # （實作測試時複製 result 改 term_key 寫第二學期）
```

- [ ] **Step 2: fail** → **Step 3: 實作**

```python
def build_v1(out_dir, generated_at):
    from ntut_catalog.periods import build_period_table
    canonical = out_dir / "canonical"
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()):
        term = term_dir.name
        courses = [CourseOffering.model_validate_json(l)
                   for l in (term_dir/"catalog.ndjson").read_text(encoding="utf-8").splitlines() if l.strip()]
        year, sem = int(term.split("-")[0]), int(term.split("-")[1])
        cat = TermCatalog(term=TermInfo(key=term, year=year, semester=sem,
                                        label=f"{year} 學年度第 {sem} 學期"),
                          generated_at=None, courses=courses)
        v1 = out_dir/"v1"/"terms"/term
        v1.mkdir(parents=True, exist_ok=True)
        (v1/"catalog.json").write_text(cat.model_dump_json(), encoding="utf-8")
        (v1/"classes.json").write_text((term_dir/"classes.json").read_text(encoding="utf-8"), encoding="utf-8")
        (v1/"periods.json").write_text(build_period_table().model_dump_json(), encoding="utf-8")
        # 最新 snapshot → enrollment.json
        snaps = sorted((term_dir/"enrollment").glob("*.ndjson"))
        counts = {}
        observed = None
        if snaps:
            for line in snaps[-1].read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                r = json.loads(line)
                counts[r["offering_id"]] = Enrollment(enrolled_count=r["enrolled_count"],
                    withdrawn_count=r["withdrawn_count"], observed_at=r["observed_at"])
                observed = r["observed_at"]
        (v1/"enrollment.json").write_text(
            EnrollmentLatest(term_key=term, observed_at=observed, counts=counts).model_dump_json(),
            encoding="utf-8")
    write_manifest(out_dir, generated_at)
```

（imports：在 artifacts.py 頂部補 `from models import CourseOffering, TermCatalog, TermInfo, EnrollmentLatest, Enrollment` 等。）

- [ ] **Step 4: PASS** → **Step 5: commit** `feat(crawler): build complete v1 from canonical + manifest`

### Task A5: CLI 改走 canonical + skip-check + build_v1 整合

**Files:** Modify `crawler/ntut_catalog/cli.py`；Test `crawler/tests/test_cli.py`

- [ ] **Step 1: 失敗測試**（skip 檢查改看 canonical）

```python
def test_crawl_skip_checks_canonical(tmp_path, monkeypatch):
    # canonical 已存在 → 非 force 應 skip；force 應重爬
    from ntut_catalog import cli
    (tmp_path/"canonical"/"115-1").mkdir(parents=True)
    (tmp_path/"canonical"/"115-1"/"catalog.ndjson").write_text("{}\n")
    assert cli.term_already_done(tmp_path, "115-1") is True
    assert cli.term_already_done(tmp_path, "114-1") is False
```

- [ ] **Step 2: fail** → **Step 3: 實作**：
  - 新增 `term_already_done(out_dir, term)`：`(out_dir/"canonical"/term/"catalog.ndjson").exists()`。
  - crawl 迴圈：skip 判斷改用 `term_already_done`；每學期 `crawl_term` 後改呼叫 `write_canonical(result, out_dir)` + `write_enrollment_snapshot(result, out_dir, today)`（today = `datetime.now(TAIPEI).strftime("%Y-%m-%d")`）；**不再** write_term。
  - 迴圈結束後呼叫 `build_v1(out_dir, now_iso)`（重建完整 v1 + manifest）。
  - 移除舊 `write_term` import（保留函式或刪除，見 Task A6 遷移後）。
- [ ] **Step 4: 全測試 PASS**：`.venv/bin/pytest -q`（修既有 test_orchestrator 對 write_term 的引用：改驗 write_canonical/build_v1 產物）。
- [ ] **Step 5: commit** `refactor(crawler): crawl writes canonical + builds v1; skip-check on canonical`

### Task A6: 既有 11 學期離線遷移

**Files:** Create `crawler/ntut_catalog/migrate.py`；Test `crawler/tests/test_migrate.py`；CLI `migrate` 子命令

把現有 `data/`（含 inline enrollment 的 catalog）→ 新 canonical（structural catalog + classes.json + seed enrollment snapshot），再 `build_v1`。seed snapshot 日期取每課 `observed_at` 的日期（同一批爬取，統一用其日期）。

- [ ] **Step 1: 失敗測試**（造一個舊格式 term → 遷移 → 驗證）

```python
def test_migrate_existing_term(tmp_path):
    # 舊格式：canonical/115-1/catalog.ndjson 內嵌 enrollment + v1/.../classes.json
    # 遷移後：catalog.ndjson 結構化、enrollment/{date}.ndjson 出現、build_v1 還原 enrollment.json
    ...
    from ntut_catalog.migrate import migrate_all
    migrate_all(tmp_path, "2026-06-13T02:00:00+08:00")
    nd = json.loads((tmp_path/"canonical"/"115-1"/"catalog.ndjson").read_text().splitlines()[0])
    assert nd["enrollment"]["enrolled_count"] is None
    assert list((tmp_path/"canonical"/"115-1"/"enrollment").glob("*.ndjson"))
```

- [ ] **Step 2: fail** → **Step 3: 實作 `migrate.py`**：
  - 讀現有 `canonical/{term}/catalog.ndjson`（舊格式含 enrollment）→ 對每課抽 enrollment → 寫 `enrollment/{date}.ndjson`（date 取 observed_at 前 10 字，缺則用傳入 fallback date）→ structural_course 重寫 catalog.ndjson。
  - 把現有 `v1/terms/{term}/classes.json` 複製到 `canonical/{term}/classes.json`（若 canonical 沒有）。
  - 全部 term 處理完 → `build_v1(out_dir, generated_at)`。
  - 冪等：再跑一次無變化（catalog 已結構化 → enrolled_count 已 None → snapshot 用同 date 覆寫）。
  - CLI `migrate` 子命令呼叫 `migrate_all`。
- [ ] **Step 4: 測試 PASS** → **Step 5: 對真實資料跑**：`.venv/bin/python -m ntut_catalog migrate --out ../data`，然後驗證：

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path; import json
from models import CourseOffering, Manifest, TermCatalog, EnrollmentLatest
d = Path("../data")
man = Manifest.model_validate_json((d/"v1/manifest.json").read_text())
assert len(man.terms) == 11
for t in man.terms:
    # canonical 結構化
    for l in (d/"canonical"/t/"catalog.ndjson").read_text().splitlines():
        c = CourseOffering.model_validate_json(l); assert c.enrollment.enrolled_count is None
    assert (d/"canonical"/t/"classes.json").exists()
    assert list((d/"canonical"/t/"enrollment").glob("*.ndjson"))
    # v1 還原 enrollment
    enr = EnrollmentLatest.model_validate_json((d/"v1/terms"/t/"enrollment.json").read_text())
    assert enr.counts
print("migrate OK: 11 terms structural + snapshots + v1 rebuilt")
EOF
```

- [ ] **Step 6: 確認內嵌 pool kind 仍正確**（migrate 經 structural_course→model_copy，classes 欄不動）：抽查 115-1 一門 pool 課 kind==pool。
- [ ] **Step 7: commit**（暫存於 main，Task C2 再移到 data branch）`feat(crawler): offline migrate 11 terms to structural canonical + snapshots`

---

## Phase B — 發佈

### Task B1: `infra/redline_scan.py`（資料紅線掃描）

**Files:** Create `infra/redline_scan.py`；Test `crawler/tests/test_redline.py`（或 `infra/tests/`）

擋：學號樣式（`\b1\d{8}\b` 北科學號常見 9 碼，保守用「連續8+數字疑似學號」需排除課號6碼）、`Cookie:`/`Set-Cookie`/`JSESSIONID`/`session`/`password`/`Authorization:`、完整 HTML 錯誤頁標記（`查詢選課資料出現錯誤`、`<html`）。掃 `data/canonical/**`。

- [ ] **Step 1: 失敗測試**

```python
from infra.redline_scan import scan_text, scan_paths
def test_scan_flags_secrets():
    assert scan_text("JSESSIONID=abc")[0:1]  # 命中
    assert scan_text("查詢選課資料出現錯誤")
    assert scan_text("password: 1234")
def test_scan_clean_passes():
    assert scan_text('{"offering_id":"366392","enrolled_count":73}') == []
```

- [ ] **Step 2: fail** → **Step 3: 實作** scan_text(regex list)→hits、scan_paths(glob)→{path:hits}、`__main__` 非空則 `sys.exit(1)` 印違規。
- [ ] **Step 4: PASS** → 對真實 canonical 跑一次應乾淨：`.venv/bin/python infra/redline_scan.py ../data/canonical`。
- [ ] **Step 5: commit** `feat(infra): canonical data redline scanner`

### Task B2: `infra/publish.py`（quality gate + 原子 wrangler 發佈 + dry-run）

**Files:** Create `infra/publish.py`；Test `crawler/tests/test_publish.py`

職責：① `build_v1`（呼叫 artifacts，確保完整）② quality gate ③ 逐檔 wrangler put（term files 先、manifest 最後）。dry-run 不呼叫 wrangler、印計畫。

- [ ] **Step 1: 失敗測試**（純函式部分：key 對映、quality gate、上傳順序）

```python
from infra.publish import r2_key, cache_control_for, quality_gate, plan_uploads

def test_r2_key_prefix():
    assert r2_key("v1/terms/115-1/catalog.json") == "course/v1/terms/115-1/catalog.json"
def test_cache_control():
    assert "max-age=300" in cache_control_for("manifest.json")
    assert "max-age=3600" in cache_control_for("terms/115-1/catalog.json")
    assert "max-age=300" in cache_control_for("terms/115-1/enrollment.json")
def test_quality_gate_blocks_drop():
    ok, msg = quality_gate(current=100, previous=200, min_ratio=0.95)
    assert ok is False
    assert quality_gate(current=2440, previous=2450, min_ratio=0.95)[0] is True
    assert quality_gate(current=0, previous=0, min_ratio=0.95)[0] is False  # 0 課必擋
def test_plan_uploads_manifest_last():
    files = ["v1/terms/115-1/catalog.json", "v1/manifest.json", "v1/terms/115-1/enrollment.json"]
    plan = plan_uploads(files)
    assert plan[-1].endswith("manifest.json")     # manifest 最後
```

- [ ] **Step 2: fail** → **Step 3: 實作**：
  - `r2_key(rel)`：`"course/" + rel`（rel 形如 `v1/...` → `course/v1/...`）。
  - `cache_control_for(rel)`：manifest/enrollment→`public, max-age=300`；其餘→`public, max-age=3600`。
  - `quality_gate(current, previous, min_ratio)`：current==0→(False,...)；previous>0 且 current<previous*min_ratio→(False,...)；else (True,"")。
  - `plan_uploads(files)`：term files 排前、manifest 最後。
  - `wrangler_put(bucket, key, path, content_type, cache_control, dry_run)`：dry_run 印；否則 `subprocess.run(["wrangler","r2","object","put", f"{bucket}/{key}", "--file", path, "--content-type", content_type, "--cache-control", cache_control], check=True)`。
  - `main(argv)`：argparse `--bucket --terms --all --dry-run --min-ratio --previous-counts`；流程 build_v1 → 對每 term 算 current vs previous（previous 由 `--previous-counts` 或讀上一版 canonical 行數，workflow 傳入）→ gate → plan_uploads → put（term files 全 OK 後才 put manifest）。
- [ ] **Step 4: PASS** → dry-run 實測：`.venv/bin/python infra/publish.py --bucket ntutbox-cdn --terms 115-1 --dry-run`（印 key + headers，不需憑證）。
- [ ] **Step 5: commit** `feat(infra): R2 publish (quality gate + atomic + dry-run)`

### Task B3: `infra/r2-cors.json`

**Files:** Create `infra/r2-cors.json`

```json
[{"AllowedOrigins":["https://course.ntutbox.com","http://localhost:3000"],
  "AllowedMethods":["GET","HEAD"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":86400}]
```

- [ ] commit `feat(infra): R2 CORS policy`

---

## Phase C — Workflow / 文件 / 分支

### Task C1: `.gitignore` main 擋整個 `data/`

**Files:** Modify `.gitignore`

- [ ] 把 `data/v1/`、`data/*-log-*.txt` 區塊整併為 `data/`（main 不放任何 data；canonical 在 `data` branch）。保留註解說明。commit `chore: ignore all data/ on main (canonical lives on data branch)`

### Task C2: orphan `data` branch 重整（本地 git，含 filter-repo）

**Files:** git 結構（無檔案內容變更）

- [ ] **Step 1: 安全備份**：`git branch backup/pre-data-split`（可回復點）。記下目前 HEAD。
- [ ] **Step 2: 確認 migrate 後的 canonical 已 commit 在 main**（Task A6 Step 7）。
- [ ] **Step 3: 建 orphan `data` branch，root=canonical 樹**：

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git checkout --orphan data
git rm -rf --quiet .                      # 清 index
git checkout main -- data/canonical       # 取出 canonical
# 把 data/canonical/* 提到 branch root
git mv data/canonical/* . 2>/dev/null || (shopt -s dotglob; for t in data/canonical/*; do git mv "$t" .; done)
rmdir data/canonical data 2>/dev/null || true
git commit -m "data: canonical catalog/classes/enrollment snapshots (110-1..115-1)"
git checkout main
```

（注意：`git mv` 互動限制下用迴圈；確保 data branch root 直接是 `{term}/...`。）
- [ ] **Step 4: 從 main 歷史移除 data/canonical**（repo 未 push，安全）：優先 `git filter-repo --path data/canonical --invert-paths --force`；若未安裝則 `pip install git-filter-repo` 或退而用 `git rm -r --cached data/canonical && git commit`（接受歷史殘留，記錄於報告）。
- [ ] **Step 5: 驗證**：`git checkout main && ls data 2>/dev/null`（應無或僅 gitignored）；`git checkout data && ls`（應見 `115-1/ 114-2/ ...`）；`git checkout main`。
- [ ] **Step 6: 不 commit 額外**（branch 操作本身即結果）。記錄於最終報告。

### Task C3: `.github/workflows/crawl.yml`

**Files:** Create `.github/workflows/crawl.yml`

- [ ] 內容（要點）：
  - `on: schedule: cron '0 20 * * *'` + `workflow_dispatch: inputs: terms, force`。**無 push trigger**。
  - `permissions: contents: write`；`concurrency: group: crawl, cancel-in-progress: false`。
  - job：
    1. `actions/checkout`（main）。
    2. `actions/checkout`（`ref: data, path: data/canonical`）。
    3. setup-python 3.12 + `pip install -e ./crawler`（或 uv）。
    4. 決定 TERMS：`inputs.terms` → 否則 `vars.ACTIVE_TERMS` → 否則 `python -m ntut_catalog current-term`；對非自動值跑 regex 驗證。
    5. 記 previous counts：`wc -l data/canonical/{term}/catalog.ndjson`（每 term）。
    6. `python -m ntut_catalog crawl --terms $TERMS --force --out data`。
    7. `python infra/redline_scan.py data/canonical`（fail→停）。
    8. commit+push **data branch**：在 `data/canonical` 內 `git add -A`；分 catalog/classes diff 與 enrollment snapshot 兩訊息；`git pull --rebase origin data` 後 `git push`。
    9. `python infra/publish.py --bucket ${{ vars.R2_BUCKET }} --terms $TERMS --previous-counts <json>`（env 帶 `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`）。
  - **本地無法跑 Actions**：本任務只產出 YAML 並用 `yamllint`/`python -c "import yaml; yaml.safe_load(open(...))"` 驗證語法。
- [ ] 驗證：`python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/crawl.yml')); print('yaml ok')"`。
- [ ] commit `feat(infra): GitHub Actions crawl workflow`

### Task C4: `infra/SETUP.md`

**Files:** Create `infra/SETUP.md`

- [ ] 內容：① `gh repo create`（public）+ push main & data branch；② `wrangler r2 bucket create ntutbox-cdn` + 綁 custom domain `cdn.ntutbox.com`（dashboard 步驟）+ `wrangler r2 bucket cors put ntutbox-cdn --rules @infra/r2-cors.json`；③ Cloudflare API token scopes（R2 Edit）；④ GH secrets（`CLOUDFLARE_API_TOKEN`,`CLOUDFLARE_ACCOUNT_ID`）+ variables（`ACTIVE_TERMS` 留空=自動、`R2_BUCKET=ntutbox-cdn`、quality-gate ratio）；⑤ 首次全量發佈：`python infra/publish.py --bucket ntutbox-cdn --all`；⑥ 驗證 curl。
- [ ] commit `docs(infra): go-live SETUP guide`

### Task C5: crawler README 更新

**Files:** Modify `crawler/README.md`

- [ ] 補：canonical 新佈局（structural + snapshots）、`current-term`/`migrate`/build-v1 指令、data branch 說明、infra/ 指引。commit `docs(crawler): document canonical layout + migrate/current-term + infra`

---

## 驗收（上線前完成定義）
1. `cd crawler && .venv/bin/pytest` 全綠（含新測試）。
2. `data` branch 有 11 學期 structural canonical + classes + seed enrollment snapshot；`main` 無 data（gitignored）。
3. `python -m ntut_catalog migrate` 後 `build_v1` 產的 v1 全過 pydantic 驗證、manifest 涵蓋 11 學期、內嵌 pool kind 正確。
4. `publish.py --dry-run` 印正確 R2 key + cache headers；quality gate 對殘缺資料會擋。
5. `redline_scan.py` 對 canonical 乾淨。
6. `crawl.yml` YAML 合法；`current-term` live 印 `115-1`。
7. **未**建 repo/bucket、未 push、未設 secrets、未 live publish（留給使用者最後確認）。
8. 產出架構圖 + 流程圖（Mermaid）。

## 自我檢查（spec 對照）
- structural catalog（去 volatile + 去 timestamp + 非 mutate）→ A2 ✓
- enrollment snapshot 時序 → A3 ✓
- classes 進 canonical → A3/A6 ✓
- build-v1 完整重建 + manifest 涵蓋全學期 → A4 ✓
- detect-current-term + ACTIVE_TERMS override → A1/C3 ✓
- skip-check 改 canonical + daily --force → A5/C3 ✓
- 11 學期遷移 → A6 ✓
- quality gate + 原子發佈 + dry-run → B2 ✓
- CORS → B3 ✓
- 紅線掃描 → B1 ✓
- orphan data branch + main 擋 data → C1/C2 ✓
- workflow（雙 checkout/concurrency/rebase/輸入驗證/commit 拆分） → C3 ✓
- SETUP（資源建立留給使用者） → C4 ✓
