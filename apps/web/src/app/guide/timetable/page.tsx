import type { Metadata } from "next";
import { FactTable } from "@/components/guide/FactTable";
import { GuideList, GuideNote, GuideSection } from "@/components/guide/GuideSection";
import { GuideShell } from "@/components/guide/GuideShell";
import {
  PERIOD_TABLE,
  REQUIREMENT_LEGEND,
  SOURCE_GAPS,
} from "@/lib/guide/facts";
import { guideMetadata, guidePageBySlug, otherGuidePages } from "@/lib/guide/pages";
import { buildBreadcrumbJsonLd, buildGuideArticleJsonLd, guidePageBreadcrumb } from "@/lib/guide/schema";

const PAGE = guidePageBySlug("timetable");

export const metadata: Metadata = guideMetadata(PAGE);

export default function TimetableGuidePage() {
  const breadcrumb = guidePageBreadcrumb(PAGE);
  return (
    <GuideShell
      breadcrumb={breadcrumb}
      jsonLd={[buildBreadcrumbJsonLd(breadcrumb), buildGuideArticleJsonLd(PAGE)]}
      heading={PAGE.heading}
      lead={
        <p>
          北科大課表上的「第 N 節」「第 A 節」不是打錯字。全校的節次是
          <strong className="font-semibold text-[var(--ink)]">
            {" "}1、2、3、4、N、5、6、7、8、9、A、B、C、D{" "}
          </strong>
          共 14 節——中午有一節 N，晚上是 A 到 D。第一次看課表被這個卡住是很正常的。
          這頁把節次時間、課號與課程編碼的差別、修別符號的意思整理成一張一張表。
        </p>
      }
      related={otherGuidePages(PAGE.slug)}
    >
      <GuideSection id="periods" title="節次與上課時間對照">
        <p>
          節次順序是 1–4，接著中午的 N，然後 5–9，最後是晚上的 A–D。
          所以「三 5、6」是星期三下午 13:10 到 15:00，「一 A、B」是星期一晚上 18:30 到 20:10。
        </p>
        <FactTable
          caption="北科大節次與上課時間對照表"
          head={["節次", "上課時間", "時段"]}
          rows={PERIOD_TABLE.map((p) => [
            p.token,
            `${p.start}–${p.end}`,
            p.token === "N" ? "中午" : "ABCD".includes(p.token) ? "晚上" : "白天",
          ])}
        />
        <GuideList
          items={[
            <>
              <strong className="font-semibold text-[var(--ink)]">中午的 N</strong>
              ：12:10–13:00，是一個正式的節次，真的會有課排在這裡。
            </>,
            <>
              <strong className="font-semibold text-[var(--ink)]">晚上的 A–D</strong>
              ：18:30 起，A 與 B、C 與 D 之間沒有下課時間（B 從 19:20 接著 A 的結束）。
            </>,
            <>
              第 9 節（17:10–18:00）到 A 節之間有一段空檔，這段常被當成晚餐時間。
            </>,
          ]}
        />
        <GuideNote>
          <p>
            這張表來自課程查詢系統結果頁下方由學校列出的節次時間表，本站的爬蟲每次抓取
            都會對照該頁重新驗證一次時刻。若學校調整作息，以學校公告為準。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="ids" title="課號和課程編碼是兩個不同的東西">
        <p>
          查課時會看到兩組代碼，很容易混在一起，但用途完全不同：
        </p>
        <FactTable
          layout="wide"
          caption="課號與課程編碼的差別"
          head={["", "課號", "課程編碼"]}
          rows={[
            ["長相", "6 位數字（例如 360744）", "英數混合（例如 2A00001）"],
            ["代表什麼", "這一學期、這一班的這門課", "這門課本身的身分，跨學期固定"],
            ["會不會變", "每學期重新編，同一門課不同學期不同號", "不會變"],
            ["一對多", "一個課號只對一個開課班次", "同一個編碼可以對到多個課號（多班開課）"],
            ["用來做什麼", "選課系統認的就是課號；查課綱、分享課程也用它", "對照課程標準、找同一門課的其他班"],
          ]}
        />
        <GuideList
          items={[
            "要跟同學講「我在說哪一班」，講課號最準確。",
            "想找「同一門課但別的老師／別的時間」，用課程編碼或課名搜尋比較快。",
            "本站的課程分享連結帶的是學期 + 課號，所以換學期後同一條連結不會指到同一門課。",
          ]}
        />
      </GuideSection>

      <GuideSection id="symbols" title="修別符號：○△☆●▲★">
        <p>
          開課清單裡課名旁邊的符號代表必選修類別。學校在課程標準頁附有圖例，對照如下：
        </p>
        <FactTable
          layout="wide"
          caption="修別符號對照表"
          head={["符號", "必／選", "類別", "開課清單常見度"]}
          rows={REQUIREMENT_LEGEND.map((r) => [
            r.symbol,
            r.kind,
            r.label,
            r.seenInCatalog ? "常見" : "本站資料中未出現",
          ])}
        />
        <p>
          記法很簡單：形狀看層級——
          <strong className="font-semibold text-[var(--ink)]">圓形＝部訂、三角＝校訂、星形＝選修</strong>
          ；填色看範圍——<strong className="font-semibold text-[var(--ink)]">空心＝共同科目、實心＝專業科目</strong>。
          所以 ☆ 是共同選修、★ 是專業選修。
        </p>
        <GuideNote>
          <p>
            「開課清單常見度」是對本站收錄的歷年開課資料統計的結果：實際出現的只有
            △、▲、☆、★ 四種，○ 與 ● 在官方圖例上有、但開課清單中沒有出現過。
            符號代表的類別是全校通用的，但某一門課算不算你的必修，仍要看你所屬系所年級的
            課程標準。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="language" title="英文授課（EMI）怎麼看">
        <p>
          課程查詢系統有一個「授課語言」欄位，值可能是「英語」或「中英雙語」；沒有標註的
          就是沒有特別註明。本站把它做成篩選條件，可以只看英文授課、或把英文授課排除掉。
        </p>
        <p>
          這個欄位在來源就有，只是官方查詢頁欄位很多、容易被忽略；一些第三方查課工具因為
          解析時抓錯欄位而整欄空白，所以「別的站看不到」不代表這門課沒標。
        </p>
      </GuideSection>

      <GuideSection id="official-vs-here" title="官方查詢系統與本站的差別">
        <GuideList
          items={[
            <>
              官方課程查詢系統有
              <strong className="font-semibold text-[var(--ink)]"> 電腦版與手機版兩個入口，後端是同一支</strong>
              。手機版比較好讀，但欄位被壓縮（教師、班級、教室變成純文字、沒有代碼連結），
              學校自己在頁尾註明手機版資料僅供參考、正式資料以電腦版為主。
            </>,
            <>
              本站把電腦版的完整欄位整理成可搜尋的資料，每日更新，並補上官方查詢做不到的
              部分：全文搜尋、多條件篩選、把課排進週課表、即時算學分與衝堂。
            </>,
            <>
              但本站
              <strong className="font-semibold text-[var(--ink)]">不能也不會代你選課</strong>
              ——沒有登入、不碰學校系統。它的定位是「開放選課前先把課表想清楚」。
            </>,
          ]}
        />
      </GuideSection>

      <GuideSection id="gaps" title="這份資料查不到的欄位（也就是本站不會有的）">
        <p>
          有些資訊在公開的課程查詢系統裡根本不存在，所以任何整理自它的工具都不可能有。
          誠實列出來，免得你以為是本站沒做：
        </p>
        <FactTable
          layout="wide"
          caption="課程查詢系統來源缺少的資訊"
          head={["查不到", "為什麼"]}
          rows={SOURCE_GAPS.map((g) => [g.what, g.why])}
        />
        <GuideNote tone="caution" title="所以衝堂判斷有精度上限">
          <p>
            本站的衝堂偵測是比對兩門課「星期 × 節次」有沒有重疊。遇到隔週上課、
            只上半學期、或分組上課的課，這種判斷可能過度警告或漏警告——這類課請自己看
            課程備註與課綱確認。
          </p>
        </GuideNote>
      </GuideSection>
    </GuideShell>
  );
}
