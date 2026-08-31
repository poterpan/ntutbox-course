import type { Metadata } from "next";
import Link from "next/link";
import { FactTable } from "@/components/guide/FactTable";
import { GuideList, GuideNote, GuideSection } from "@/components/guide/GuideSection";
import { GuideShell } from "@/components/guide/GuideShell";
import { MPROGRAM_CATEGORIES } from "@/lib/guide/facts";
import { OAA_MPROGRAM_URL } from "@/lib/planner/mprogram-links";
import { guideMetadata, guidePageBySlug, otherGuidePages } from "@/lib/guide/pages";
import { buildBreadcrumbJsonLd, buildGuideArticleJsonLd, guidePageBreadcrumb } from "@/lib/guide/schema";

const PAGE = guidePageBySlug("micro-programs");

export const metadata: Metadata = guideMetadata(PAGE);

/** 分類的字面說明——只說「這個標記代表課程在學程中的層級」，不宣稱各層級的應修門數。 */
const CATEGORY_HINT: Record<string, string> = {
  基礎: "入門、先修性質的課程",
  核心: "該學程的主幹課程",
  總整: "收尾、整合性質的課程（capstone）",
  進階: "在核心之上的深入課程",
  應用: "偏實作與應用場景的課程",
};

export default function MicroProgramsGuidePage() {
  const breadcrumb = guidePageBreadcrumb(PAGE);
  return (
    <GuideShell
      breadcrumb={breadcrumb}
      jsonLd={[buildBreadcrumbJsonLd(breadcrumb), buildGuideArticleJsonLd(PAGE)]}
      heading={PAGE.heading}
      lead={
        <p>
          微學程最常見的誤會是把它當成「加一門課」。實際上是兩件獨立的事：
          <strong className="font-semibold text-[var(--ink)]">課要照常在選課系統選</strong>
          ，而
          <strong className="font-semibold text-[var(--ink)]">「加入這個微學程」是教務處的登記修讀程序</strong>
          ，不經選課系統。只做其中一件，另一件不會自動完成。
        </p>
      }
      related={otherGuidePages(PAGE.slug)}
    >
      <GuideSection id="what" title="微學程是什麼">
        <p>
          112 學年度起入學之日間部大學部，畢業前須完成跨領域學習（微學程為五種路徑之一）；
          修讀須於教務處公告期間登記。也就是說，微學程對部分學生不只是加分項，而是畢業要求的
          其中一條路徑。
        </p>
        <p>
          完整的規章、申請方式與各學程的課程標準在教務處的
          {" "}
          <a
            href={OAA_MPROGRAM_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--accent-ink)] underline underline-offset-2"
          >
            微學程公告頁
          </a>
          ；本站不重製那些文件。
        </p>
      </GuideSection>

      <GuideSection id="two-things" title="選課與登記修讀是兩件事">
        <FactTable
          layout="wide"
          caption="選課與微學程登記修讀的差別"
          head={["", "選課", "登記修讀微學程"]}
          rows={[
            ["在哪裡做", "選課系統（初選／加退選）", "教務處的登記程序，不在選課系統裡"],
            ["做什麼", "把某一門課加進你這學期的課表", "把你納入某個微學程的修讀名單"],
            ["什麼時候", "依選課階段的開放時間", "由教務處公告，和選課開放時間不一定相同"],
            ["漏掉會怎樣", "沒選到課，這學期就沒修", "課修完了，但不會被認列成這個微學程"],
          ]}
        />
        <GuideNote tone="caution" title="兩邊都要做">
          <p>
            把微學程的課全部修完、卻沒有完成登記，通常不會自動被認列。
            登記的方式、期限與資格條件請看教務處與該學程開課單位的公告——這頁不寫日期，
            因為每年不同。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="categories" title="微學程的課有分類：基礎、核心、總整…">
        <p>
          在學程的課程清單裡，每門課會標一個分類，代表它在這個學程中的角色：
        </p>
        <FactTable
          caption="微學程課程分類"
          head={["分類", "大致意思"]}
          rows={MPROGRAM_CATEGORIES.map((c) => [c, CATEGORY_HINT[c] ?? ""])}
        />
        <GuideNote>
          <p>
            這些分類名稱來自學校課程標準頁上的標記。
            <strong className="font-semibold text-[var(--ink)]">
              每個學程要在各分類修幾門、總共幾學分才算完成，各學程規定不同
            </strong>
            ——本站在學程詳情頁附上學校「相關規定」的原文，請直接讀那段，不要用別的學程的
            規則推論。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="online" title="有些課是線上課程，不走選課系統">
        <p>
          部分微學程的課程清單裡會有線上課程（ewant 平台）。這類課
          <strong className="font-semibold text-[var(--ink)]">不在選課系統開班</strong>
          ，所以你在課程查詢裡怎麼找都找不到——那不是資料漏抓，是它本來就不在那裡。
        </p>
        <p>
          本站會把這類課標成「線上課程」，而不是顯示成「未開課」的灰色狀態，
          免得你誤以為這門課停開了。修習方式請依該學程的公告辦理。
        </p>
      </GuideSection>

      <GuideSection id="how-to-take" title="微學程的課要怎麼排、怎麼選">
        <GuideList
          items={[
            "微學程的課本身就是一般開課的課程，用課號在選課系統選，沒有特別的通道。",
            "所以它同樣受選課階段限制：如果那門課不是你本班的，一樣要等開學後加退選。",
            "要確認一門課算不算在某個學程內，看該學程的課程清單最準；本站的微學程頁就是用學校公布的學程課程清單比對，不是用課程備註推測。",
            "同一門課可能同時屬於多個微學程；反過來，一個微學程的課會散在不同系所開課。",
          ]}
        />
        <p>
          選課階段的差別另見
          {" "}
          <Link href="/guide/selection-phases/" className="text-[var(--accent-ink)] underline underline-offset-2">
            選課注意事項
          </Link>
          。
        </p>
      </GuideSection>

      <GuideSection id="browse-here" title="在本站怎麼看微學程">
        <GuideList
          items={[
            "排課器裡有微學程瀏覽：可以列出當學期的微學程、看每個學程的課程清單與學校規定原文。",
            "篩選列有「微學程」三態按鈕：關閉／只看微學程的課／把微學程的課排除。",
            "從學程清單點進課程，可以直接排進週課表，順便看時間衝不衝。",
          ]}
        />
        <GuideNote>
          <p>
            本站只呈現整理後的課程清單與規定原文，完整的規章、申請表單與 PDF 只在教務處與
            開課單位的官網；本站不重製那些文件，也不代為判斷你是否符合修讀資格。
          </p>
        </GuideNote>
      </GuideSection>
    </GuideShell>
  );
}
