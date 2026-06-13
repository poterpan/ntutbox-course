# 系統架構 / 資料管線

> 北科盒子排課系統的資料側架構（爬蟲 → canonical → R2 → 前端）。
> 設計依據：`DECISIONS.md`、`DESIGN.md`、`superpowers/specs/2026-06-13-infra-data-pipeline-design.md`。

## 1. 系統架構

```mermaid
flowchart TB
    subgraph src["資料來源（公開免登入）"]
        ntut["aps.ntut.edu.tw/course/tw/<br/>QueryCourse · Subj · QueryCurrPage"]
    end

    subgraph compute["運算：GitHub Actions（cron 04:00 台北）"]
        crawler["crawler / ntut_catalog<br/>(限流+退避 · 表頭定位解析)"]
        buildv1["build_v1<br/>canonical → 完整 v1"]
        gate["quality gate + 紅線掃描"]
    end

    subgraph git["git（單一 repo, 兩 branch）"]
        main["main branch<br/>code only（輕 clone）"]
        databr["data branch (orphan)<br/>canonical: catalog.ndjson(結構)<br/>+ classes.json + enrollment/{date}.ndjson"]
    end

    subgraph serve["出口：Cloudflare（egress $0）"]
        r2["R2 bucket: ntutbox-cdn<br/>course/v1/..."]
        cdn["cdn.ntutbox.com/course/v1/<br/>(邊緣 gzip/br · ETag · Cache-Control)"]
    end

    subgraph clients["消費端"]
        web["Web 排課器 (P1)<br/>course.ntutbox.com"]
        ios["北科盒子 iOS App"]
    end

    ntut -->|"爬取"| crawler
    crawler -->|"write_canonical + snapshot"| databr
    databr -->|"重建"| buildv1
    buildv1 --> gate
    gate -->|"wrangler put（term files→manifest 最後）"| r2
    r2 --> cdn
    cdn -->|"fetch JSON + manifest 輪詢"| web
    cdn -->|"fetch JSON"| ios
    main -.->|"P1 部署 (CF Pages, root=apps/web)"| web
```

## 2. 每日管線流程

```mermaid
flowchart TD
    A["cron / 手動 dispatch"] --> B["checkout main(code) + data(canonical)"]
    B --> C{"指定 terms?"}
    C -->|"有"| C1["regex 驗證"]
    C -->|"無"| C2["detect_current_term<br/>(讀 QueryCurrPage 下拉)"]
    C1 --> D
    C2 --> D["crawl --force 當前學期"]
    D --> E["write 結構化 catalog.ndjson<br/>+ classes.json + enrollment snapshot"]
    E --> F["紅線掃描<br/>(學號/cookie/token/HTML 錯誤頁)"]
    F -->|"命中"| FX["✗ fail，停止"]
    F -->|"乾淨"| G{"canonical 有變?"}
    G -->|"結構變"| G1["commit data(catalog)"]
    G -->|"enrollment"| G2["commit data(enrollment)"]
    G1 --> H
    G2 --> H["push → data branch"]
    H --> I["build_v1：從全部 canonical 重建完整 v1 + manifest"]
    I --> J{"quality gate<br/>課數 ≥ 上次×95% 且 >0 ?"}
    J -->|"否"| JX["✗ 不發佈（防殘缺資料）"]
    J -->|"是"| K["wrangler put：term files → 驗證 → manifest 最後"]
    K --> L["R2 / cdn.ntutbox.com"]
```

## 3. 資料模型分層（為何 catalog 與 enrollment 分離）

```mermaid
flowchart LR
    subgraph canonical["canonical（git data branch · 完整真相）"]
        cat["catalog.ndjson<br/>純結構 · 無人數/時間戳<br/>→ 結構沒變則每日零 diff"]
        cls["classes.json<br/>系所/年級/班級 + kind(pool…)"]
        snap["enrollment/{date}.ndjson<br/>每日時序快照（人數/撤選）"]
    end

    subgraph v1["v1（R2 · 由 canonical 重建 · 可丟棄）"]
        v1cat["catalog.json<br/>(結構 envelope · sha=版本)"]
        v1cls["classes.json"]
        v1per["periods.json (節次↔牆鐘)"]
        v1enr["enrollment.json<br/>(最新 overlay)"]
        man["manifest.json<br/>(sha256/size/dataset_version)"]
    end

    cat --> v1cat
    cls --> v1cls
    snap -->|"最新一筆"| v1enr
    v1cat & v1cls & v1per & v1enr --> man

    web["Web：catalog（結構，快取久）<br/>+ enrollment overlay（短快取）<br/>以 offering_id 整體取代合併"]
    v1cat -.-> web
    v1enr -.-> web
```

## 設計要點對照
- **運算在 GitHub Actions、出口在 Cloudflare R2**：R2 只能被 push（無「CF 拉 git」）；Worker 跑不動爬蟲（D6）。CF git 整合留給 P1 web 部署。
- **canonical 完整可重建 v1**：CI 發佈前重建全部學期 → manifest 永遠涵蓋全學期、與 R2 物件一致。
- **catalog 純結構 + enrollment 分離**：避免每日 3MB 無意義 diff；git 歷史＝乾淨的 enrollment 時序（比 gnehs inline-people 更省）。
- **自動偵測當前學期**：學校學期末才上架下學期、開學後凍結 → 只爬偵測到的學期即足夠。
- **守門**：紅線掃描擋個資/機密進公開 repo；quality gate 擋殘缺資料發佈；原子發佈（manifest 最後推）。
- **未做（fast-follow）**：選課季 enrollment-only 高頻爬取（見 infra spec）。
