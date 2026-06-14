import { dataBaseUrl } from "@/lib/env";
import { HttpDataSource } from "./cdn-datasource";
import type { DataSource } from "./datasource";

let _ds: DataSource | null = null;
export function getDataSource(): DataSource {
  if (!_ds) _ds = new HttpDataSource(dataBaseUrl());
  return _ds;
}
export type { DataSource } from "./datasource";
