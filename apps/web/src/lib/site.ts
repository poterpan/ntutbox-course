/** 正式站 origin。metadata canonical / JSON-LD / worker 改寫的 canonical 必須一致
 * （worker 另有一份同值常數：它跑在不同 runtime，見 worker/index.ts 註解）。 */
export const SITE_ORIGIN = "https://course.ntutbox.com";

/** 站名（品牌）。其他頁 title 模板 `%s｜北科盒子 排課`、JSON-LD name、PWA name 都用它。
 * ⚠️ worker（lib/share/og.ts）與 use-course-title 的課程 title 後綴也是這個字串，改站名要一起改。 */
export const SITE_NAME = "北科盒子 排課";

/** 首頁 title：品牌詞「北科排課」放最前（主攻搜尋字），站名與功能詞在後。
 * 唯一來源：layout.tsx 的 metadata.title.default 與 use-course-title 的 HOME_TITLE 都讀這裡。
 * 分享連結（/?course=、/?plan=）的 title 由 edge worker 換成課名，不吃這個值。 */
export const HOME_TITLE = "北科排課｜北科盒子・北科大選課、課表規劃與課程查詢";

/** 首頁 description（也用在 OG/Twitter、WebApplication JSON-LD、PWA manifest）。 */
export const HOME_DESCRIPTION =
  "免登入的北科排課工具：北科大（國立臺北科技大學）課程查詢與課綱瀏覽，排週課表時即時檢查衝堂與學分。選課前先規劃好，可分享課表或匯入北科盒子 App。";
