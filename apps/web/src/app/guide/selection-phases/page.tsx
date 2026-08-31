import type { Metadata } from "next";
import Link from "next/link";
import { FactTable } from "@/components/guide/FactTable";
import { GuideList, GuideNote, GuideSection } from "@/components/guide/GuideSection";
import { GuideShell } from "@/components/guide/GuideShell";
import { SELECTION_ERRORS, SELECTION_MECHANISMS } from "@/lib/guide/facts";
import { guideMetadata, guidePageBySlug, otherGuidePages } from "@/lib/guide/pages";
import { buildBreadcrumbJsonLd, buildGuideArticleJsonLd, guidePageBreadcrumb } from "@/lib/guide/schema";

const PAGE = guidePageBySlug("selection-phases");

export const metadata: Metadata = guideMetadata(PAGE);

export default function SelectionPhasesGuidePage() {
  const breadcrumb = guidePageBreadcrumb(PAGE);
  return (
    <GuideShell
      breadcrumb={breadcrumb}
      jsonLd={[buildBreadcrumbJsonLd(breadcrumb), buildGuideArticleJsonLd(PAGE)]}
      heading={PAGE.heading}
      lead={
        <p>
          「北科的選課」不是一個系統、一個窗口。它至少分成
          <strong className="font-semibold text-[var(--ink)]">
            {" "}期末網路初選、志願選填分發、開學後加退選、獨立登記{" "}
          </strong>
          四種機制，各自能處理的課不一樣。搞混這件事最常見的後果就是：在初選一直送一門
          註定會被退的課，或是等到加退選才發現想修的課早就該在初選處理掉了。
        </p>
      }
      related={otherGuidePages(PAGE.slug)}
    >
      <GuideSection id="mechanisms" title="四種機制一次看懂">
        <FactTable
          layout="wide"
          caption="北科大選課的四種機制與各自的範圍"
          head={["機制", "在哪裡處理", "處理哪些課"]}
          rows={SELECTION_MECHANISMS.map((m) => [
            m.name,
            m.where,
            <ul key={m.name} className="ml-4 list-disc space-y-1">
              {m.scope.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>,
          ])}
        />
        <div className="space-y-3">
          {SELECTION_MECHANISMS.map((m) => (
            <div key={m.name}>
              <p className="font-semibold text-[var(--ink)]">{m.name}</p>
              <p className="mt-0.5">{m.note}</p>
            </div>
          ))}
        </div>
        <GuideNote tone="caution" title="日期每年不同，這頁不寫">
          <p>
            各階段的開放與截止時間每學期公告都不一樣，寫在這裡只會過期。
            請以教務處當學期的選課公告為準；本頁只講「哪一類課在哪個機制處理」這件不太會變的事。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="preselection" title="期末網路初選：只有你「有資格直接選」的課">
        <p>
          初選能直接選的，主要是你本班的課，加上同系較低年級的選修課程。
          跨系、跨班的課通常不在這個階段的範圍內。
        </p>
        <p>
          送出時系統會同時檢查兩件事：
          <strong className="font-semibold text-[var(--ink)]">這個開課班級是不是在你被授權的範圍內</strong>
          、以及
          <strong className="font-semibold text-[var(--ink)]">這門課是不是真的屬於那個班級</strong>
          。兩者只要有一個不對就會被退，所以「填別班的班級代碼去搶別班的課」在初選階段是行不通的。
        </p>
        <GuideNote>
          <p>
            這段的行為是由本站開發者用自己的帳號實測（測試後全數退掉）得到的結論，
            不是校方公布的錯誤碼文件。系統行為可能隨年度改版而改變。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="ballot" title="志願選填：博雅、體育、共同英文不是先搶先贏">
        <p>
          博雅課程、體育、共同英文這幾類，在初選期間走的是
          <strong className="font-semibold text-[var(--ink)]">填志願、由系統分發</strong>
          ，不是按下加選就進去。所以：
        </p>
        <GuideList
          items={[
            "重點是志願順序，不是誰先按——但還是要在公告的期限內完成填寫。",
            "分發結果出來之前，你排在課表上的那一門只是「希望」，可能不會是最後上到的那一門。",
            "共同英文是以學年分班分發（上學期填、下學期不再填），和一般課程的邏輯不同。",
            "體育（含專科四年級）同樣走志願分發；大學部三、四年級的體育選修則是在開學後加退選處理。",
          ]}
        />
        <p>
          排課時建議把這類課「先排上去佔位」，但心裡知道它是浮動的——真正確定的是分發結果。
          通識與體育的細節另見
          {" "}
          <Link href="/guide/general-education/" className="text-[var(--accent-ink)] underline underline-offset-2">
            通識課程怎麼選
          </Link>
          。
        </p>
      </GuideSection>

      <GuideSection id="add-drop" title="開學後加退選：跨系跨班與特殊類別的主場">
        <p>
          很多課本來就只在加退選階段才處理，包括跨系跨班修讀，以及創新創業、國際觀培養、
          臺北聯大跨校通識博雅／全英語、大學部三四年級體育選修、自主學習、跨域專題這幾類。
        </p>
        <p>
          這代表：如果你想修的課不是本班的，在初選一直嘗試也不會成功——正確做法是先把它排進
          課表當規劃，等加退選再處理。本站的排課器不會阻止你排入這類課，因為「可規劃」和
          「這個階段可送出」是兩件事。
        </p>
      </GuideSection>

      <GuideSection id="registration" title="獨立登記：微學程、輔系、雙主修不在選課系統裡">
        <p>
          微學程與學程的「登記修讀」、輔系、雙主修，走的是教務處的登記程序，
          <strong className="font-semibold text-[var(--ink)]">不是選課動作</strong>
          。課還是要照常在選課系統選，登記只是把你納入該學程的修讀名單。
        </p>
        <p>
          兩邊都要做，漏掉登記的話就算課全修完也不會被算成學程。微學程的部分另見
          {" "}
          <Link href="/guide/micro-programs/" className="text-[var(--accent-ink)] underline underline-offset-2">
            微學程怎麼修
          </Link>
          。
        </p>
      </GuideSection>

      <GuideSection id="errors" title="常見回應訊息是什麼意思">
        <p>
          選課系統的訊息偏行政語言，看不出下一步該做什麼。這幾條是最常遇到的：
        </p>
        <FactTable
          layout="wide"
          caption="選課系統常見回應訊息對照"
          head={["訊息", "意思", "下一步"]}
          rows={SELECTION_ERRORS.map((e) => [e.message, e.meaning, e.next])}
        />
        <GuideNote tone="caution" title="這張表是實測整理，不是官方文件">
          <p>
            訊息文字與行為都可能隨系統改版變動，且同一句話在不同情境下未必是同一個原因。
            若遇到這裡沒列到的訊息或情況與描述不符，請以學校選課系統與教務處的說明為準。
          </p>
        </GuideNote>
      </GuideSection>

      <GuideSection id="checklist" title="排課前先確認這幾件事">
        <GuideList
          items={[
            "把想修的課逐一標記「這門在哪個機制處理」——初選能送的、要等加退選的、要另外登記的，分開列。",
            "初選清單按想要的程度排好順序：如果一次送多門，學分上限一擋住，排在後面的就進不去了。",
            "衝堂先在排課階段解決掉，不要留到開放當下才發現。",
            "學分上下限、以及某門課這學期到底開不開，一律以學校系統當下的提示為準——公開的課程資料看不到人數上限，也看不到班週會與導師時間佔掉的時段。",
          ]}
        />
      </GuideSection>
    </GuideShell>
  );
}
