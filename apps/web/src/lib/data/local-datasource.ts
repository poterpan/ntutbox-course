// Local fixtures share HTTP semantics (served from /public). Kept as a named export
// so the abstraction is explicit and future local-only behavior can diverge.
export { HttpDataSource as LocalDataSource } from "./cdn-datasource";
