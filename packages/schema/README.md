# packages/schema — 資料合約（單一真相）

資料合約的**單一真相是 `crawler/models.py`（Pydantic v2）**。本套件負責由它生成其他語言型別，避免三端漂移：

```
crawler/models.py  ──model_json_schema()──▶  schema.json
                                              ├─▶ TS 型別（web 用；json-schema-to-typescript / quicktype）
                                              └─▶ Swift Codable（未來 iOS 用）
```

## 待辦
- 加一支 script：跑 Pydantic `model_json_schema()` 匯出 `schema.json`，再產 `index.d.ts`/`index.ts`。
- 納入 CI：schema 變動時自動重生並檢查 web 型別。

> 為何不在 web 端手刻型別：保證 crawler 輸出與 web 消費同源。iOS（Swift Codable）日後同法由 schema.json 生成。
