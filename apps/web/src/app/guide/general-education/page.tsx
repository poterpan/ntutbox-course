import type { Metadata } from "next";
import Link from "next/link";
import { FactTable } from "@/components/guide/FactTable";
import { GuideList, GuideNote, GuideSection } from "@/components/guide/GuideSection";
import { GuideShell } from "@/components/guide/GuideShell";
import { GE_DIMENSIONS } from "@/lib/guide/facts";
import { guideMetadata, guidePageBySlug, otherGuidePages } from "@/lib/guide/pages";
import { buildBreadcrumbJsonLd, buildGuideArticleJsonLd, guidePageBreadcrumb } from "@/lib/guide/schema";

const PAGE = guidePageBySlug("general-education");

export const metadata: Metadata = guideMetadata(PAGE);

/** 各向度的一句話說明——只描述字面語意，不宣稱這是通識中心的官方定義。 */
const DIMENSION_HINT: Record<string, string> = {
  人文與藝術: "文學、歷史、哲學、音樂、美學、影像這一類",
  社會與法治: "法律、政治、經濟、社會與公民議題這一類",
  自然與科學: "生命科學、環境、數理與應用科技這一類",
  創新與創業: "創業實務、創新思考、管理與財務入門這一類",
};

export default function GeneralEducationGuidePage() {
  const breadcrumb = guidePageBreadcrumb(PAGE);
  return (
    <GuideShell
      breadcrumb={breadcrumb}
      jsonLd={[buildBreadcrumbJsonLd(breadcrumb), buildGuideArticleJsonLd(PAGE)]}
      heading={PAGE.heading}
      lead={
        <p>
          通識這一塊和專業課的玩法不一樣：博雅課程、體育、共同英文在初選期間多半是
          <strong className="font-semibold text-[var(--ink)]">填志願、由系統分發</strong>
          ，不是先搶先贏。而且查課時你會看到一些看起來很奇怪的東西——班級欄寫著
          「博雅課程(三)」、有些課 0 學分、有些課名叫「請選…」。這頁把這些一次講清楚。
        </p>
      }
      related={otherGuidePages(PAGE.slug)}
    >
      <GuideSection id="overview" title="北科通識大致分成哪幾塊">
        <FactTable
          layout="wide"
          caption="通識相關課程的類別"
          head={["類別", "開課單位", "特徵"]}
          rows={[
            [
              "博雅課程",
              "通識中心",
              "每門 2 學分，備註欄會標示所屬向度；初選走志願分發。",
            ],
            [
              "體育",
              "體育室",
              "以「體育專項」的形式開課、學分為 0；大學部三、四年級的體育選修在開學後加退選處理。",
            ],
            [
              "共同英文",
              "開課單位依年度而異",
              "以學年為單位分班分發（上學期填志願、下學期不再填）。",
            ],
            [
              "校訂共同必修",
              "各系與通識中心",
              "國文這類全校共同科目，修別符號通常是 △；不走志願分發，屬本班課程。同一門共同科目可能由各系自己開班。",
            ],
          ]}
        />
        <GuideNote>
          <p>
            這張表描述的是課程資料呈現出來的樣子（開課單位、學分、備註），不是通識中心的
            課程架構文件。各類別要修幾學分、哪些能互相抵充，以通識中心與教務處公告為準。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="dimensions" title="博雅課程的四個向度">
        <p>
          博雅課程在課程備註欄會標示它屬於哪一個向度。本站收錄的資料中，出現過的向度有四個：
        </p>
        <FactTable
          caption="博雅課程的向度"
          head={["向度", "大致是哪些課"]}
          rows={GE_DIMENSIONS.map((d) => [d, DIMENSION_HINT[d] ?? ""])}
        />
        <p>
          在本站查課時，向度是寫在課程備註裡的，可以直接用關鍵字搜尋（例如搜「人文與藝術」）
          把該向度的課找出來，再看時間排不排得下。
        </p>
        <GuideNote tone="caution" title="要修幾個向度、每個向度幾學分，這頁不寫">
          <p>
            「四個向度」是我們從課程備註觀察到的分類名稱；每位學生要在各向度修多少學分、
            不同入學年度與學制的要求差異，本站無法查證，所以不寫。
            這部分請看通識中心與教務處針對你入學年度的規定。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="ballot" title="博雅怎麼選：志願分發，不是先搶先贏">
        <GuideList
          items={[
            "初選期間，博雅走的是填志願、由系統分發，重點是志願順序而不是按鈕速度。",
            "所以「開放瞬間狂點」對這類課沒有幫助；把志願想清楚、在期限內填完比較重要。",
            "分發結果出來前，排課表上的博雅只是規劃——最後上到哪一門要看分發結果。",
            "臺北聯大跨校的通識博雅（含全英語）不在初選處理，是開學後加退選的範圍。",
          ]}
        />
        <p>
          各機制的差別另見
          {" "}
          <Link href="/guide/selection-phases/" className="text-[var(--accent-ink)] underline underline-offset-2">
            選課注意事項
          </Link>
          。
        </p>
      </GuideSection>

      <GuideSection id="pool-classes" title="為什麼班級欄寫著「博雅課程(三)」？">
        <p>
          查博雅或體育的課時，「開課班級」不會是你的班，而是像
          <strong className="font-semibold text-[var(--ink)]">
            {" "}博雅課程(一)～(十四)、職博雅課程(一)(二)、體育專項(一)～(十六){" "}
          </strong>
          這種名字。這些不是真的班級，而是
          <strong className="font-semibold text-[var(--ink)]">課程池</strong>
          ——全校學生共用的一個容器，所以任何學生的班級代碼都不會出現在裡面。
        </p>
        <GuideList
          items={[
            "看到這種班級名稱，代表這門課不是靠「本班／外班」判斷可不可選的，而是走志願分發或另外的規則。",
            "換句話說，如果你拿「這門課的班級不是我的班」去推論「所以我不能選」，在這類課上會判斷錯。",
            "「職博雅課程」是進修部（夜間）的博雅池，命名邏輯相同。",
          ]}
        />
        <GuideNote>
          <p>
            本站在整理資料時會把這種班級標記成課程池，避免把博雅、體育、英文誤判成
            「外班課程」。這也是為什麼本站不會替你斷言「這門課你一定選得到」——
            個人的可選範圍只有登入學校系統才知道。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="placeholders" title="「請選…」這種課是什麼？">
        <p>
          課程資料裡有一批課，課名以「請選」開頭、或者 0 學分且沒有教師與教室。
          這些是
          <strong className="font-semibold text-[var(--ink)]">佔位課</strong>
          ：它們在課表上代表「這個時段你有一門通識／體育要修」，但實際上哪一門要另外選（或等分發）。
        </p>
        <GuideList
          items={[
            "佔位課不是可以上課的實體課程，把它當成一個提醒欄位比較貼近。",
            "計算學分時要把 0 學分的佔位課排除，不然會算不對。",
            "體育專項的學分是 0，這是資料本來的樣子，不是本站漏抓。",
          ]}
        />
      </GuideSection>

      <GuideSection id="pe-english" title="體育與共同英文的兩個容易踩到的點">
        <FactTable
          layout="wide"
          caption="體育與共同英文的注意事項"
          head={["", "要注意什麼"]}
          rows={[
            [
              "體育",
              "初選期間走志願分發（含專科四年級）；但大學部三、四年級的體育選修是在開學後加退選階段處理，別在初選一直等。",
            ],
            [
              "共同英文",
              "以學年為單位分班分發：上學期填志願，下學期不再填。所以下學期查不到要填的地方通常是正常的，不是漏掉。",
            ],
          ]}
        />
        <GuideNote tone="caution">
          <p>
            分班與分發的規則會依年度與學制調整，也可能有系所例外。這頁只講一般情形，
            實際狀況請看當學期公告。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="search-here" title="在本站怎麼把通識課找出來">
        <GuideList
          items={[
            "用開課單位篩選：博雅走通識中心、體育走體育室，一次就能把範圍縮到通識這一塊。",
            "用向度關鍵字搜尋（例如「社會與法治」）找特定向度的課。",
            "用時間篩選：先看你課表上還空著的時段，再去找那個時段有開的通識，比一門一門試快很多。",
            "英文授課（EMI）可以單獨篩選，想修全英語通識時很好用。",
          ]}
        />
        <p>
          排進課表後本站會即時算衝堂與學分；但要記得志願分發類的課，排上去只是規劃。
        </p>
      </GuideSection>
    </GuideShell>
  );
}
