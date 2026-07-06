# OG 圖源稿

`og-image.html`（1200×630）是 `public/og.jpg` 的源稿。改文案/視覺 → 改 HTML → 重截 → commit。

重截（macOS，在 `apps/web/og/` 下執行）：

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --headless=new --screenshot="$(pwd)/og-tmp.png" \
      --window-size=1200,630 --hide-scrollbars \
      "file://$(pwd)/og-image.html"
    sips -s format jpeg -s formatOptions 85 og-tmp.png --out ../public/og.jpg && rm og-tmp.png

（icon 用同目錄 `icon-tile.jpg`＝Icon Composer 匯出的白底圓角磚，squircle 滿版、角落為黑，
CSS `border-radius: 23%` 裁黑角；換 icon 就換這個檔。）
選 JPEG 是因為 PNG 版 330KB 超過 300KB 目標、q85 JPEG 104KB 且此類漸層+色塊圖視覺無差；
若日後畫面加入透明或銳利細節需求再回 PNG（並同步改 `layout.tsx` 的 images 路徑）。
