#!/usr/bin/env python3
"""Embed the plan clauses so a Chinese question can find an English rule.

This is the one place in the project where the language gap has to be crossed
inside the maths rather than by a model reading both sides. The questions
arrive as 「600 平能不能切两块」; the rules are English legal prose. A
monolingual encoder puts those in unrelated regions of the space and retrieval
quietly returns nothing useful — quietly being the problem, because the answer
still reads fluently, just sourced from the wrong clause.

So the model is multilingual, and which one is a setting rather than a decision
buried in the code: MODELS below is a table, `--model` picks a row, and each
row writes its vectors to its own table. Two models can sit in the database at
once, which is what lets evals/plan_cases.jsonl compare them on this corpus
instead of on someone else's benchmark.

The prefixes matter more than they look. E5 models are trained with "query: "
and "passage: " markers and lose a chunk of their retrieval quality without
them, in the way that never raises an error and never looks broken — you get
plausible neighbours that are slightly wrong. BGE does not use them. Getting
this backwards is invisible except in the eval numbers, which is exactly why
it lives in the table next to the model name.

    python3 scripts/build_embeddings.py                 # default model
    python3 scripts/build_embeddings.py --model e5-small
    python3 scripts/build_embeddings.py --list
"""
import argparse
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKL_DATA_DIR", ROOT / "data"))
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))

# name -> (huggingface id, dimensions, query prefix, passage prefix)
MODELS = {
    "e5-base": ("intfloat/multilingual-e5-base", 768, "query: ", "passage: "),
    "e5-small": ("intfloat/multilingual-e5-small", 384, "query: ", "passage: "),
    "bge-m3": ("BAAI/bge-m3", 1024, "", ""),
}
# BGE-M3 wins on this project's bilingual, zone-filtered eval set: 97%
# recall@5 / 0.82 MRR versus e5-base's 90% / 0.72, with zero off-zone hits
# for both filtered paths. Keep the decision beside the model registry so the
# pipeline, CLI and future exports all select the same tested encoder.
DEFAULT = "bge-m3"


def table_for(model):
    return "plan_vec_" + model.replace("-", "_")


def passage(row):
    """What actually gets embedded.

    The clause number and title are prepended to the body because a lot of what
    distinguishes one standard from another is its name — "Building height" vs
    "Height in relation to boundary" — while their bodies read almost the same.
    Chapter is included so a question naming a zone has something to match.
    """
    chapter_title, clause_id, title, text = row
    return f"{chapter_title} — {clause_id} {title}\n\n{text}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT, choices=sorted(MODELS))
    ap.add_argument("--list", action="store_true", help="show what is embedded already")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    if not DB.exists():
        sys.exit(f"{DB} not found — run scripts/build_db.py first")
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false;")

    if args.list:
        for name in sorted(MODELS):
            t = table_for(name)
            exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                [t]).fetchone()[0]
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if exists else 0
            hf, dim, _, _ = MODELS[name]
            mark = "*" if name == DEFAULT else " "
            print(f" {mark} {name:<10} {dim:>5}d  {n:>5} vectors  {hf}")
        return

    if not con.execute("SELECT count(*) FROM information_schema.tables "
                       "WHERE table_name = 'plan_clause'").fetchone()[0]:
        sys.exit("plan_clause is missing — run scripts/build_plan.py first")

    hf_id, dim, q_prefix, p_prefix = MODELS[args.model]
    rows = con.execute("""
        SELECT clause_key, chapter, clause_id, title, text
        FROM plan_clause ORDER BY clause_key
    """).fetchall()
    print(f"{len(rows):,} clauses -> {args.model} ({hf_id}, {dim}d)")

    # Skipped rather than failed when the ML stack is absent. This runs as a
    # build step, and CI installs duckdb and pyarrow, not two gigabytes of
    # torch — it builds the page, which needs no vectors. A missing encoder
    # there is a normal outcome, not a broken run.
    try:
        from sentence_transformers import SentenceTransformer  # heavy; import late
    except ImportError:
        print("  sentence-transformers not installed — skipping embeddings.\n"
              "  install it to build them:  pip install sentence-transformers")
        return

    t0 = time.time()
    model = SentenceTransformer(hf_id)
    print(f"  model loaded in {time.time() - t0:.1f}s")

    texts = [p_prefix + passage(r[1:]) for r in rows]
    t0 = time.time()
    vecs = model.encode(texts, batch_size=args.batch, normalize_embeddings=True,
                        show_progress_bar=False)
    took = time.time() - t0
    if vecs.shape[1] != dim:
        sys.exit(f"model returned {vecs.shape[1]}d, MODELS says {dim}d")
    print(f"  encoded in {took:.1f}s ({len(rows) / took:.0f} clauses/s)")

    table = table_for(args.model)
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} (
            clause_key TEXT PRIMARY KEY, embedding FLOAT[{dim}]);
    """)
    con.executemany(f"INSERT INTO {table} VALUES (?, ?)",
                    [(r[0], v.tolist()) for r, v in zip(rows, vecs)])

    # Recorded so retrieval cannot pair a query prefix with the wrong table,
    # and so a stale set of vectors is visible rather than merely old.
    con.execute("""
        CREATE TABLE IF NOT EXISTS embedding_run (
            model TEXT PRIMARY KEY, hf_id TEXT, dims INTEGER,
            query_prefix TEXT, passage_prefix TEXT,
            clauses INTEGER, built_at TIMESTAMP, seconds DOUBLE);
    """)
    con.execute("DELETE FROM embedding_run WHERE model = ?", [args.model])
    con.execute("INSERT INTO embedding_run VALUES (?,?,?,?,?,?,now(),?)",
                [args.model, hf_id, dim, q_prefix, p_prefix, len(rows), took])
    con.execute("CHECKPOINT")
    con.close()
    print(f"wrote {len(rows):,} vectors -> {table}")


if __name__ == "__main__":
    main()
