"""產物輸出：canonical NDJSON（git）+ v1 JSON artifacts（→ R2）+ manifest。

佈局（docs/DESIGN.md §4.5）：
  data/canonical/{term}/catalog.ndjson      一行一課（diff/審查/重建用）
  data/v1/terms/{term}/catalog.json         TermCatalog（web 主檔）
  data/v1/terms/{term}/classes.json         ClassDirectory
  data/v1/terms/{term}/periods.json         PeriodTable
  data/v1/terms/{term}/enrollment.json      EnrollmentLatest（volatile overlay）
  data/v1/manifest.json                     sha256/size/dataset_version
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from models import Manifest, ManifestEntry, ManifestTerm
from ntut_catalog.orchestrator import TermResult


def write_term(result: TermResult, out_dir: Path) -> None:
    term = result.catalog.term.key
    canonical = out_dir / "canonical" / term
    canonical.mkdir(parents=True, exist_ok=True)
    with (canonical / "catalog.ndjson").open("w", encoding="utf-8") as f:
        for course in result.catalog.courses:
            f.write(course.model_dump_json(exclude_none=False) + "\n")

    v1 = out_dir / "v1" / "terms" / term
    v1.mkdir(parents=True, exist_ok=True)
    for name, model in [
        ("catalog.json", result.catalog),
        ("classes.json", result.classes),
        ("periods.json", result.periods),
        ("enrollment.json", result.enrollment),
    ]:
        (v1 / name).write_text(model.model_dump_json(), encoding="utf-8")


def _entry(path: Path, rel_url: str) -> ManifestEntry:
    data = path.read_bytes()
    return ManifestEntry(url=rel_url, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def write_manifest(out_dir: Path, generated_at: str) -> Manifest:
    terms_dir = out_dir / "v1" / "terms"
    terms = {}
    for term_dir in sorted(terms_dir.iterdir()) if terms_dir.exists() else []:
        if not term_dir.is_dir():
            continue
        term = term_dir.name
        files = {}
        for name in ["catalog", "classes", "periods", "enrollment"]:
            p = term_dir / f"{name}.json"
            if p.exists():
                files[name] = _entry(p, f"terms/{term}/{name}.json")
        if "catalog" not in files:
            continue
        # dataset_version 取該學期 catalog 的 generated_at（client 比對用）
        gen = json.loads((term_dir / "catalog.json").read_text(encoding="utf-8")).get("generated_at")
        terms[term] = ManifestTerm(
            catalog=files["catalog"],
            classes=files.get("classes"),
            periods=files.get("periods"),
            enrollment=files.get("enrollment"),
            dataset_version=gen,
        )
    manifest = Manifest(generated_at=generated_at, terms=terms)
    (out_dir / "v1" / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest
