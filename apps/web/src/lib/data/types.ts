// Single source of truth: types generated from crawler/models.py (Pydantic).
// Regenerate: cd packages/schema && pnpm generate
export type {
  TermCatalog,
  CourseOffering,
  PeriodTable,
  PeriodRef,
  ClassDirectory,
  ClassRef,
  EnrollmentLatest,
  Enrollment,
  Manifest,
  ManifestTerm,
  Meeting,
} from "../../../../../packages/schema/index";

// App-side bundle of one term's files.
export interface TermBundle {
  termKey: string;
  catalog: import("../../../../../packages/schema/index").TermCatalog;
  periods: import("../../../../../packages/schema/index").PeriodTable;
  classes: import("../../../../../packages/schema/index").ClassDirectory;
  enrollment: import("../../../../../packages/schema/index").EnrollmentLatest | null;
}
