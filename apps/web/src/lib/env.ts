// Resolves the v1 data base URL. Dev default = local fixtures under /data/v1.
// Prod sets NEXT_PUBLIC_DATA_BASE_URL=https://cdn.ntutbox.com/course/v1
export function dataBaseUrl(): string {
  const v = process.env.NEXT_PUBLIC_DATA_BASE_URL?.trim();
  return v && v.length > 0 ? v.replace(/\/$/, "") : "/data/v1";
}
export function isLocalData(): boolean {
  return dataBaseUrl().startsWith("/");
}
