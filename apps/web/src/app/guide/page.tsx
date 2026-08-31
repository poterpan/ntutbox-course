import type { Metadata } from "next";
import { GuideCardLink } from "@/components/guide/GuideCardLink";
import { GuideNote, GuideSection } from "@/components/guide/GuideSection";
import { GuideShell } from "@/components/guide/GuideShell";
import { GUIDE_INDEX, GUIDE_PAGES, GUIDE_PATH } from "@/lib/guide/pages";
import { buildBreadcrumbJsonLd, guideIndexBreadcrumb } from "@/lib/guide/schema";

export const metadata: Metadata = {
  title: GUIDE_INDEX.title,
  description: GUIDE_INDEX.description,
  // ⚠️ root layout 把 canonical 釘在 "/"（分享連結全指首頁）；子路由必須自己覆蓋，
  // 否則整個 /guide/* 會 canonical 到首頁而不被索引。
  alternates: { canonical: GUIDE_PATH },
  openGraph: {
    type: "article",
    url: GUIDE_PATH,
    title: GUIDE_INDEX.title,
    description: GUIDE_INDEX.description,
  },
};

export default function GuideIndexPage() {
  const breadcrumb = guideIndexBreadcrumb();
  return (
    <GuideShell
      breadcrumb={breadcrumb}
      jsonLd={[buildBreadcrumbJsonLd(breadcrumb)]}
      heading={GUIDE_INDEX.heading}
      lead={
        <>
          <p>
            北科大的查課與選課有幾個一開始很容易踩到的坑：節次不是 1 到 14、
            「選課」其實分成好幾種機制、通識博雅不是先搶先贏、微學程要另外登記。
            這幾頁把這些整理成可以先看懂再動手的說明。
          </p>
          <p className="mt-2">
            本站是排課工具，資料每日整理自校方公開的課程查詢系統；這些指南是為了讓你在
            排課之前先搞清楚制度怎麼運作。制度細節一律以學校公告為準。
          </p>
        </>
      }
    >
      <GuideSection id="pages" title="四個主題">
        <div className="grid gap-3 sm:grid-cols-2">
          {GUIDE_PAGES.map((page) => (
            <GuideCardLink key={page.slug} page={page} />
          ))}
        </div>
      </GuideSection>

      <GuideSection id="how-to-use" title="建議的使用順序">
        <p>
          如果你是第一次排課，照這個順序看比較不會白做工：
        </p>
        <ol className="ml-4 list-decimal space-y-1.5">
          <li>
            先看懂課表怎麼讀（節次、課號、修別符號），才知道查到的課在星期幾的幾點上。
          </li>
          <li>
            再確認每一門想修的課「屬於哪個選課機制」——有些課初選就能選，有些一定要等
            開學後加退選，先分清楚可以省掉很多失敗的送出。
          </li>
          <li>
            通識博雅、體育、共同英文另外看一頁：它們多半走志願分發，排課的思路和專業課不同。
          </li>
          <li>
            要修微學程的話，記得「選課」和「登記修讀」是兩件事，兩邊都要做。
          </li>
        </ol>
      </GuideSection>

      <GuideSection id="scope" title="這些頁面刻意沒寫的東西">
        <GuideNote tone="caution" title="會逐年變動的細節，我們不寫">
          <p>
            選課各階段的起訖日期、每學期的學分上下限、各類別的應修學分與畢業學分——
            這些每學年公告都可能不同，寫在靜態頁面上只會過期並害人誤判。
            這類數字請直接看教務處與各開課單位當年度的公告與選課系統當下的提示。
          </p>
        </GuideNote>
        <p>
          同樣地，本站無法得知你個人的可選課範圍（那要登入學校系統才知道）。
          指南裡談的是制度的一般規則，不是對你個人狀況的判斷。
        </p>
      </GuideSection>
    </GuideShell>
  );
}
