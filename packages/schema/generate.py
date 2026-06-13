"""Dump a combined JSON Schema (with $defs) for the v1 file roots from crawler/models.py.
Run: python packages/schema/generate.py  → writes packages/schema/schema.json
Then: pnpm --filter @ntutbox/schema generate  → index.d.ts via json-schema-to-typescript
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crawler"))

from models import (  # noqa: E402
    TermCatalog, PeriodTable, ClassDirectory, EnrollmentLatest, Manifest,
)

ROOTS = {
    "TermCatalog": TermCatalog,
    "PeriodTable": PeriodTable,
    "ClassDirectory": ClassDirectory,
    "EnrollmentLatest": EnrollmentLatest,
    "Manifest": Manifest,
}

def main() -> None:
    combined: dict = {"title": "NtutboxCourseV1", "type": "object", "properties": {}, "$defs": {}}
    for name, model in ROOTS.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        for dname, dschema in schema.pop("$defs", {}).items():
            combined["$defs"][dname] = dschema
        combined["$defs"][name] = schema
        combined["properties"][name] = {"$ref": f"#/$defs/{name}"}
    out = Path(__file__).with_name("schema.json")
    out.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
