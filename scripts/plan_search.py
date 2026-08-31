#!/usr/bin/env python3
"""Find the plan clauses that answer a question about a particular place.

The retrieval here is filtered before it is scored, and that ordering is the
point of the whole design. A parcel's zone is not something to be guessed from
the wording of a question — it is a fact the database already holds, resolved
by point-in-polygon at build time. So the zone picks the chapter, and the
vectors only choose which clause inside it.

Unfiltered, "how tall can I build" is a question 24 chapters answer, each with
a different number, all of them phrased almost identically; the nearest
neighbour is then a coin toss that reads like an answer. Filtered, the same
question has one chapter's worth of candidates and the wrong-zone answer is not
merely unlikely, it is unreachable.

Region-wide chapters — subdivision, natural hazards — carry no zone codes and
are always in scope, because they apply everywhere.

One thing that looked obvious and was not: stripping the zone name out of the
question before embedding it, on the theory that the filter has already settled
the zone and repeating it in the text only spends similarity on a solved
problem. "建筑高度限制是多少" ranks H5.6.4 Building height first;
"Mixed Housing Urban 区能建多高" ranks it ninth, which looked like the zone
name doing the damage. It was not. Stripping the name sent H5.6.4 past
twentieth, and Single House from eighth to fifteenth. The difference was never
the zone — it is that one query is a well-formed noun phrase and the other is a
colloquial fragment, and taking words out makes the fragment shorter. What
retrieval is weak at here is short spoken-style questions, which is a thing to
measure in evals/plan_cases.jsonl rather than to guess at twice.

    python3 scripts/plan_search.py "600 平的地能不能切成两块" --zone 18
    python3 scripts/plan_search.py "how tall can I build" --suburb Remuera
    python3 scripts/plan_search.py "recession plane" --no-filter -k 3
"""
import argparse
import os
import re
import sys
from pathlib import Path

import duckdb

import build_embeddings

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKL_DATA_DIR", ROOT / "data"))
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))

_model_cache = {}


def embedding_config(con, model=None):
    """The row embedding_run recorded, so the query prefix matches the vectors."""
    model = model or build_embeddings.DEFAULT
    row = con.execute("SELECT * FROM embedding_run WHERE model = ?",
                      [model]).fetchone()
    if not row:
        sys.exit(f"no vectors for '{model}' — "
                 f"run scripts/build_embeddings.py --model {model}")
    return {"model": row[0], "hf_id": row[1], "dims": row[2],
            "query_prefix": row[3], "passage_prefix": row[4]}


def encode(question, cfg):
    from sentence_transformers import SentenceTransformer  # heavy; import late
    if cfg["hf_id"] not in _model_cache:
        _model_cache[cfg["hf_id"]] = SentenceTransformer(cfg["hf_id"])
    model = _model_cache[cfg["hf_id"]]
    return model.encode([cfg["query_prefix"] + question],
                        normalize_embeddings=True)[0].tolist()


def search(con, question, zone_code=None, k=5, model=None, chapters=None):
    """Nearest clauses, restricted to what applies where the question is about."""
    cfg = embedding_config(con, model)
    table = "plan_vec_" + cfg["model"].replace("-", "_")
    vec = encode(question, cfg)

    where, params = [], [vec]
    if zone_code is not None:
        # An empty zone_codes list means the chapter applies everywhere it is
        # not explicitly excluded — which is how E38 Subdivision - Urban states
        # its own scope, as "all zones except" the nine E39 claims.
        where.append("((len(c.zone_codes) = 0 "
                     "  AND NOT list_contains(c.excluded_zone_codes, ?)) "
                     " OR list_contains(c.zone_codes, ?))")
        params.extend([zone_code, zone_code])
    if chapters:
        where.append(f"c.chapter IN ({','.join('?' * len(chapters))})")
        params.extend(chapters)
    # Vectors are normalised at build time, so the dot product is the cosine.
    sql = f"""
        SELECT c.clause_key, c.chapter, c.clause_id, c.title, c.status,
               c.plan_changes, c.page_from, c.source_url, c.text,
               list_dot_product(v.embedding, ?::FLOAT[{cfg['dims']}]) AS score
        FROM plan_clause c JOIN {table} v USING (clause_key)
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY score DESC LIMIT {int(k)}
    """
    cols = ["clause_key", "chapter", "clause_id", "title", "status",
            "plan_changes", "page_from", "source_url", "text", "score"]
    return [dict(zip(cols, r)) for r in con.execute(sql, params).fetchall()]


def zone_for_suburb(con, suburb):
    """The zone most parcels in a suburb sit in — a convenience, not a fact
    about any one property, and labelled as such wherever it is printed."""
    row = con.execute("""
        SELECT r.planning_zone_code, z.zone, count(*) AS n
        FROM rating_unit r
        JOIN suburb s USING (suburb_id)
        JOIN planning_zone_ref z ON z.zone_code = r.planning_zone_code
        WHERE lower(s.name) = lower(?)
        GROUP BY 1, 2 ORDER BY n DESC LIMIT 1
    """, [suburb]).fetchone()
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--zone", type=int, help="planning zone code to restrict to")
    ap.add_argument("--suburb", help="use the dominant zone of this suburb")
    ap.add_argument("--no-filter", action="store_true", help="search every chapter")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--model")
    ap.add_argument("--full", action="store_true", help="print whole clause text")
    args = ap.parse_args()

    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false;")

    zone = args.zone
    if args.suburb and not args.no_filter:
        row = zone_for_suburb(con, args.suburb)
        if not row:
            sys.exit(f"no suburb named {args.suburb!r}")
        zone, zone_name, n = row
        print(f"{args.suburb}: most parcels ({n:,}) are {zone_name} [{zone}]\n")
    if args.no_filter:
        zone = None

    hits = search(con, args.question, zone_code=zone, k=args.k, model=args.model)
    for h in hits:
        flags = []
        if h["status"] != "ok":
            flags.append(h["status"].upper())
        if h["plan_changes"]:
            flags.append("/".join(h["plan_changes"]))
        print(f"{h['score']:.3f}  {h['clause_key']:<14} {h['title'][:52]}"
              f"{'   [' + ', '.join(flags) + ']' if flags else ''}")
        body = h["text"] if args.full else h["text"][:220].replace("\n", " ")
        print(f"        {body}{'' if args.full else '...'}")
        print(f"        p{h['page_from']} · {h['source_url'].rsplit('/', 1)[-1]}\n")


if __name__ == "__main__":
    main()
