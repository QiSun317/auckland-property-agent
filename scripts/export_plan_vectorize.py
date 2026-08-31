#!/usr/bin/env python3
"""Export the tested plan embeddings for Cloudflare Vectorize.

The database remains the source of truth. This script only converts its
``plan_clause`` and model-specific vector table into Vectorize's NDJSON wire
format, plus a small zone-to-chapter map used by the Worker.

The index stores one vector per clause. A query's exact planning zone is first
resolved to the chapters that govern it (for example H5 + E36 + E38), then a
Vectorize metadata filter restricts retrieval to those chapters *before*
nearest-neighbour scoring. That preserves the local evaluator's safety property
without duplicating every region-wide clause across 49 zones.

    python3 scripts/export_plan_vectorize.py
    python3 scripts/export_plan_vectorize.py --model bge-m3 --out build/plan.ndjson
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKL_DATA_DIR", ROOT / "data"))
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))
BUILD = ROOT / "build"

sys.path.insert(0, str(ROOT / "scripts"))
import build_embeddings  # noqa: E402

VECTORIZE_METADATA_LIMIT = 10 * 1024
# Leave room for implementation-level JSON accounting differences at the API.
METADATA_TARGET = 9_500
VECTORIZE_FILE_LIMIT = 100 * 1024 * 1024


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def fit_metadata(base: dict[str, Any], text: str) -> tuple[dict[str, Any], bool]:
    """Fit clause text inside Vectorize's 10 KiB per-vector metadata limit."""

    candidate = {**base, "text": text}
    if len(compact_json(candidate).encode("utf-8")) <= METADATA_TARGET:
        return candidate, False

    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        trial = {**base, "text": text[:middle].rstrip() + "…"}
        if len(compact_json(trial).encode("utf-8")) <= METADATA_TARGET:
            low = middle
        else:
            high = middle - 1
    candidate = {**base, "text": text[:low].rstrip() + "…"}
    size = len(compact_json(candidate).encode("utf-8"))
    if size > VECTORIZE_METADATA_LIMIT:
        raise ValueError(f"metadata cannot fit Vectorize limit ({size} bytes)")
    return candidate, True


def zone_map(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    rows = con.execute(
        """
        SELECT z.zone_code, z.zone,
               list_sort(list_distinct(list(c.chapter ORDER BY c.chapter))) chapters
        FROM planning_zone_ref z
        JOIN plan_clause c
          ON (len(c.zone_codes) = 0
              AND NOT list_contains(c.excluded_zone_codes, z.zone_code))
          OR list_contains(c.zone_codes, z.zone_code)
        GROUP BY z.zone_code, z.zone
        ORDER BY z.zone_code
        """
    ).fetchall()
    return {
        str(code): {"name": name, "chapters": chapters}
        for code, name, chapters in rows
    }


def export(model: str, output: Path, zones_output: Path, manifest: Path) -> None:
    if not DB.exists():
        sys.exit(f"{DB} not found — run scripts/pipeline.py run first")

    con = duckdb.connect(str(DB), read_only=True)
    run = con.execute(
        """
        SELECT hf_id, dims, query_prefix, passage_prefix, clauses, built_at
        FROM embedding_run WHERE model = ?
        """,
        [model],
    ).fetchone()
    if not run:
        sys.exit(
            f"no vectors for {model!r} — run "
            f"scripts/build_embeddings.py --model {model}"
        )
    hf_id, dims, query_prefix, passage_prefix, expected, built_at = run
    table = build_embeddings.table_for(model)
    rows = con.execute(
        f"""
        SELECT c.clause_key, c.chapter, c.clause_id, c.title,
               c.page_from, c.page_to, c.plan_changes, c.status,
               c.source_url, c.text, v.embedding
        FROM plan_clause c JOIN {table} v USING (clause_key)
        ORDER BY c.clause_key
        """
    ).fetchall()
    zones = zone_map(con)
    con.close()

    if len(rows) != expected:
        sys.exit(f"embedding run says {expected} clauses, joined export has {len(rows)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    zones_output.parent.mkdir(parents=True, exist_ok=True)
    truncated = 0
    seen: set[str] = set()
    digest = hashlib.sha256()

    with output.open("w", encoding="utf-8") as handle:
        for (
            clause_key,
            chapter,
            clause_id,
            title,
            page_from,
            page_to,
            plan_changes,
            status,
            source_url,
            text,
            embedding,
        ) in rows:
            if clause_key in seen:
                raise ValueError(f"duplicate vector id: {clause_key}")
            if len(clause_key.encode("utf-8")) > 64:
                raise ValueError(f"vector id exceeds 64 bytes: {clause_key}")
            seen.add(clause_key)
            values = list(embedding)
            if len(values) != dims:
                raise ValueError(
                    f"{clause_key} has {len(values)} dimensions; expected {dims}"
                )
            base = {
                "clause_key": clause_key,
                "chapter": chapter,
                "clause_id": clause_id,
                "title": title,
                "page_from": page_from,
                "page_to": page_to,
                "plan_changes": "/".join(plan_changes or []),
                "status": status,
                "source_url": source_url,
            }
            metadata, was_truncated = fit_metadata(base, text)
            truncated += int(was_truncated)
            line = compact_json(
                {"id": clause_key, "values": values, "metadata": metadata}
            ) + "\n"
            encoded = line.encode("utf-8")
            digest.update(encoded)
            handle.write(line)

    size = output.stat().st_size
    if size > VECTORIZE_FILE_LIMIT:
        output.unlink()
        sys.exit(
            f"export would be {size / 1024 / 1024:.1f} MiB; "
            "Vectorize upload limit is 100 MiB"
        )

    zones_output.write_text(
        json.dumps(zones, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_data = {
        "model": model,
        "hf_id": hf_id,
        "dimensions": dims,
        "query_prefix": query_prefix,
        "passage_prefix": passage_prefix,
        "embedding_built_at": str(built_at),
        "vectors": len(rows),
        "zones": len(zones),
        "metadata_texts_truncated": truncated,
        "ndjson_bytes": size,
        "sha256": digest.hexdigest(),
        "metadata_filter": "chapter",
    }
    manifest.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(rows):,} vectors · {dims}d · {size / 1024 / 1024:.1f} MiB "
        f"-> {output}"
    )
    print(f"{len(zones)} exact zone scopes -> {zones_output}")
    print(f"{truncated} long clause text(s) truncated to fit metadata limit")
    print(f"sha256 {digest.hexdigest()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=build_embeddings.DEFAULT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--zones-out", type=Path, default=BUILD / "plan-zones.json")
    parser.add_argument(
        "--manifest", type=Path, default=BUILD / "plan-vectorize-manifest.json"
    )
    args = parser.parse_args()
    output = args.out or BUILD / f"plan-vectors-{args.model}.ndjson"
    export(args.model, output, args.zones_out, args.manifest)


if __name__ == "__main__":
    main()
