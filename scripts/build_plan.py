#!/usr/bin/env python3
"""Turn the plan chapter PDFs into clauses that can be cited and checked.

Chunking by a fixed token count would be the usual thing and would be wrong
here. The plan already carries its own boundaries — H5.6.4 is one rule about
building height, complete, with its own number — and that number is the whole
point: an answer that says "11m, H5.6.4" can be checked against the source, and
an answer that cites a clause which does not exist, or which says something
else, can be caught automatically. Cut the text every 800 tokens instead and
that check has nothing to attach to.

Getting the clauses out of the PDF takes three passes, each fixing something
the previous one gets wrong:

  * The margin. Every chapter carries a narrow left-hand column of plan-change
    annotations ("PC 120 (see Modifications)") that pdftotext -layout splices
    into the body lines, so `PC 120 (see    H5.6.5. Height in relation to
    boundary` arrives as one line. Read by x-coordinate instead and the column
    separates cleanly at x<88 on a 595pt page. It is kept, not dropped: a
    clause under a live plan change is a clause whose answer needs a caveat.

  * Headings vs. cross-references. The activity table cites standards by number
    constantly, and a wrapped table cell can put `H5.6.5. Height in` alone on a
    line, trailing period and all, looking exactly like a heading. What it
    cannot fake is position: within a chapter every clause of a given depth
    sits at the same x (90 for H5.1, 108 for H5.6.1), so the modal x per depth
    identifies the real ones and the table cell at x=125 falls out. The rule
    calibrates itself per chapter rather than hardcoding the numbers, because
    the layout is not promised to be identical across chapters.

  * Order. Clause numbers should climb. Where they do not, the extraction has
    gone wrong in a way the two rules above did not catch, so it is reported
    rather than quietly accepted.

Long clauses are split, but only on their own sub-clause boundaries, and the
parts keep the parent's number: the citation still resolves to something real.

Output: the plan_clause table in data/auckland.duckdb
        data/plan_report.txt — clause counts, anomalies, what was split
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AKL_DATA_DIR", ROOT / "data"))
PLAN = Path(os.environ.get("AKL_PLAN_DIR", DATA / "raw" / "plan"))
DB = Path(os.environ.get("AKL_DB", DATA / "auckland.duckdb"))

# A4 is 595pt wide. The annotation column ends well before the body starts;
# measured across every chapter here the gap is x<88 vs x>=90.
MARGIN_X = 88
HEADER_Y = 780
# How far right of the depth-1 column a real heading can still be. Measured:
# the deepest heading column in any chapter here is 126, 36pt from the anchor;
# the nearest stray is 144.
INDENT_SPAN = 60
FOOTER = re.compile(r"^Auckland Unitary Plan\s+\w+\s+\d{4}\s*\d*$")

# Split a clause longer than this, on sub-clause boundaries only.
MAX_CHARS = 2400
# The plan's own nesting, outermost first. Only used as far down as needed.
SUBCLAUSE = [re.compile(r"^\(\d+\)\s"),
             re.compile(r"^\([a-z]\)\s"),
             re.compile(r"^\([ivx]+\)\s")]
# What the operative document prints where a plan change has removed the rule
# but its replacement is not yet operative.
PLACEHOLDER = re.compile(r"\[\s*new text to be inserted\s*\]", re.I)


def fragments(pdf):
    """(page, x, y, text) for every text run, header and footer removed.

    Position is cm x tm, not tm alone. Text drawn inside a form XObject carries
    its placement in the current transformation matrix, and reading tm by
    itself puts those runs at the origin — which silently moves real clause
    text (H3.7, H6.6.1) to (0, 0) where any sane filter then discards it.
    """
    out = []
    for page_no, page in enumerate(PdfReader(str(pdf)).pages, start=1):
        rows = []

        def visit(text, cm, tm, font, size, rows=rows):
            t = text.strip()
            if t:
                x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
                y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
                rows.append((x, y, t))

        page.extract_text(visitor_text=visit)
        for x, y, t in rows:
            if y > HEADER_Y or FOOTER.match(t):
                continue
            out.append((page_no, x, y, t))
    return out


def lines(frags):
    """Group fragments into visual lines, body and margin kept apart.

    The split is purely positional, and deliberately so. An earlier version
    tested each run against a vocabulary of things the margin is allowed to
    contain, which fails for a reason worth remembering: the annotation arrives
    as separate runs — "PC", "120", "(", "see" — so the vocabulary is matched
    against fragments, not against the phrase it was written for. "PC" alone
    matched nothing, got treated as stray body text, and the annotation ended
    up half in the margin and half in the clause.

    Measured across every chapter, x<88 holds nothing but plan-change
    annotations, the page footer, and the chapter title on page 1. The footer
    is already gone by content; the title is redundant with plan_index.json.
    So position alone is enough, and nothing has to know what the margin says.
    """
    by_line = defaultdict(list)
    for page, x, y, t in frags:
        by_line[(page, round(y))].append((x, t))
    body, margin = [], []
    for (page, y), parts in sorted(by_line.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        parts.sort()
        left = [(x, t) for x, t in parts if x < MARGIN_X]
        right = [(x, t) for x, t in parts if x >= MARGIN_X]
        if left:
            margin.append((page, y, " ".join(t for _, t in left)))
        if right:
            body.append((page, y, round(min(x for x, _ in right)),
                         " ".join(t for _, t in right)))
    return body, margin


def headings(body, chapter):
    """Real clause headings, told from cross-references by their x position.

    The trailing period is optional because the chapters disagree: H5 writes
    "H5.6.4. Building height", H9 writes "H9.6.0 Activities within 30m of a
    residential zone". Requiring it silently reduced H9 to nine section-level
    clauses over 26 pages.

    Making it optional lets every cross-reference in the activity tables in as
    a candidate — H5 alone contributes sixteen at x=288 — so position does the
    work, in two steps that between them survive every chapter here:

      * Depth-1 headings sit at x=90 in all 24 chapters, so they anchor the
        page. Deeper levels indent from there but not by a fixed amount (108 in
        H5, 126 in E36), which is why the offset is measured rather than named.
      * Among the columns within one indent of the anchor, the heading column
        is the one whose clause numbers each appear once and climb down the
        page. That is what a numbered list of rules looks like and what a
        table of cross-references cannot fake: H1 cites H1.6.7 eleven times,
        H6 cites H6.6.8 repeatedly, and those columns are neither unique nor
        ascending. Counting rows instead of testing the sequence picks the
        wrong column outright in H4, where the cross-references outnumber the
        fourteen real standards and would take H4.6.1 to H4.6.7 with them.
    """
    pat = re.compile(rf"^({re.escape(chapter)}(?:\.\d+)+)\.?\s+(\S.*)$")
    cand = []
    for i, (page, y, x, text) in enumerate(body):
        m = pat.match(text)
        if m:
            cand.append((i, page, x, m.group(1), m.group(2).strip()))

    by_depth = _by_depth(cand)
    top = by_depth.get(1)
    anchor = min(x for _, _, x, _, _ in top) if top else 90

    column = {}
    for depth, group in by_depth.items():
        by_x = defaultdict(list)
        for c in group:
            if anchor <= c[2] <= anchor + INDENT_SPAN:
                by_x[c[2]].append(c[3])
        scored = [(_run_length(ids), x) for x, ids in by_x.items()]
        best = max(scored, default=(0, None))
        column[depth] = best[1] if best[0] >= 2 else None
    kept = [c for c in cand
            if column[_depth(c[3])] is not None
            and abs(c[2] - column[_depth(c[3])]) <= 2]
    dropped = [c for c in cand if c not in kept]
    return kept, dropped


def _run_length(ids):
    """How much of this column reads as a numbered list, longest run wins.

    Length of the longest strictly increasing subsequence, which is the score
    a real heading column earns almost in full and a table of cross-references
    cannot, because it repeats numbers and revisits them. Deliberately not an
    all-or-nothing test of "is this sorted": H19's headings genuinely come out
    of order in the source, and demanding perfection there threw the whole
    chapter's depth-1 column away and left 38 pages in five chunks.
    """
    keys = [_sort_key(i) for i in ids]
    best = []
    for k in keys:
        lo, hi = 0, len(best)
        while lo < hi:
            mid = (lo + hi) // 2
            if best[mid] < k:
                lo = mid + 1
            else:
                hi = mid
        best[lo:lo + 1] = [k]
    return len(best)


def _depth(clause_id):
    return clause_id.count(".")


def _by_depth(cand):
    out = defaultdict(list)
    for c in cand:
        out[_depth(c[3])].append(c)
    return out


def _sort_key(clause_id):
    return tuple(int(p) for p in re.findall(r"\d+", clause_id))


def _siblings(clause_ids):
    """{parent clause: {child numbers}} for spotting gaps in the numbering."""
    out = defaultdict(set)
    for cid in set(clause_ids):
        parent, _, last = cid.rpartition(".")
        if parent and last.isdigit():
            out[parent].add(int(last))
    # A parent with one child says nothing about what is missing.
    return {p: k for p, k in out.items() if len(k) > 1}


def split_long(text, level=0):
    """Break an over-long clause on its own sub-clauses, never mid-rule.

    Graded, because the plan nests three deep and the levels are not evenly
    spread. H8.8.2 Assessment criteria runs to 14,563 characters under a single
    "(1)", so splitting only on that marker leaves it whole; it has sixteen
    "(a)" beneath, which cut it into pieces a retriever can tell apart. Each
    level is tried only where the one above left something still too long, so
    ordinary clauses keep their (1), (2), (3) intact rather than being diced
    down to roman numerals.
    """
    if len(text) <= MAX_CHARS or level >= len(SUBCLAUSE):
        return [text]
    marker = SUBCLAUSE[level]
    parts, cur = [], []
    for line in text.split("\n"):
        if marker.match(line.strip()) and sum(len(x) for x in cur) > MAX_CHARS * 0.6:
            parts.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    if len(parts) <= 1:
        return split_long(text, level + 1)
    return [p for part in parts for p in split_long(part, level + 1)]


def chapter_clauses(pdf, chapter, report):
    body, margin = lines(fragments(pdf))
    heads, dropped = headings(body, chapter)
    if not heads:
        report.append(f"  {chapter}: NO CLAUSES FOUND")
        return []

    # Plan-change annotations attach to whatever clause is live at their height.
    ann_at = sorted((page, y, t) for page, y, t in margin if re.search(r"PC\s*\d+", t))

    rows = []
    for n, (i, page, x, cid, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(body)
        text = "\n".join(t for _, _, _, t in body[i + 1:end]).strip()
        last_page = body[end - 1][0] if end > i else page
        pcs = sorted({m.group(0).upper().replace(" ", "")
                      for p, y, t in ann_at if page <= p <= last_page
                      for m in [re.search(r"PC\s*\d+", t)] if m})
        for part, chunk in enumerate(split_long(text), start=1):
            rows.append({
                "chapter": chapter, "clause_id": cid, "title": title,
                "part": part, "page_from": page, "page_to": last_page,
                "plan_changes": pcs, "status": "ok", "text": chunk,
            })

    # Status is settled here rather than in the loop above, because it depends
    # on something no single clause knows: whether it has children. A section
    # like "H5.6. Standards" is a bare heading by design and carries everything
    # in H5.6.1 onward — empty is correct for it and means nothing.
    #
    # An empty *leaf* is different. It can be live in the plan and blank in
    # this document, because a plan change has lifted its text and the
    # replacement is not operative yet. Sometimes "[new text to be inserted]"
    # is printed in the gap; sometimes, as with H6.6.10 Maximum impervious area
    # and H6.6.12 Landscaped area, nothing is, and only the PC annotation in
    # the margin marks it. Either way the clause exists and the activity table
    # cites it. That is not an extraction failure and must not be smoothed
    # over: asked for that number, the honest answer is that the rule is being
    # replaced — not a number invented to fill the hole, and not silence.
    ids = {r["clause_id"] for r in rows}
    for r in rows:
        has_children = any(o != r["clause_id"] and o.startswith(r["clause_id"] + ".")
                           for o in ids)
        if has_children or len(PLACEHOLDER.sub("", r["text"]).strip()) >= 40:
            continue
        r["status"] = "replaced_by_plan_change" if r["plan_changes"] else "empty"

    order = [c[3] for c in heads]
    if order != sorted(order, key=_sort_key):
        bad = [a for a, b in zip(order, sorted(order, key=_sort_key)) if a != b]
        report.append(f"  {chapter}: clause order breaks at {bad[:5]}")
    if dropped:
        report.append(f"  {chapter}: {len(dropped)} cross-reference(s) rejected as "
                      f"headings: {[d[3] for d in dropped][:5]}")
    # A section that has sub-clauses is allowed to be a bare heading — "H5.6.
    # Standards" carries nothing of its own and everything in H5.6.1 onward.
    # A leaf with no text is the one worth reporting: it means the body was
    # lost between the heading and the next one.
    # Where sub-clause headings are not found the chunks fall back to section
    # level — H9.6 Standards becomes one 14-page block instead of fifteen
    # rules. The citation is still a real clause, so nothing said becomes
    # false; it just gets less specific, which is a retrieval problem rather
    # than a correctness one. Worth saying out loud, because a chapter that
    # quietly degrades this way looks fine in the totals.
    pages = max((r["page_to"] for r in rows), default=0)
    if pages >= 8 and len(rows) and pages / len(rows) > 1.5:
        report.append(f"  {chapter}: coarse — {len(rows)} chunks over {pages} pages; "
                      f"sub-clause headings likely not detected")

    # A gap in the numbering is a clause that went missing between two that
    # did not, which the totals cannot show.
    #
    # Not every gap is recoverable. In H4 — the largest zone in the region at
    # 216,326 parcels — the standards headings print their title and not their
    # number: the text layer holds "Home occupations" where the page shows
    # "H4.6.2. Home occupations", and pdftotext reads it the same way, so the
    # number is drawn rather than written and no amount of parsing will find
    # it. Those clauses fall back to their parent section, which means the
    # citation stays true and gets less specific. Said plainly here because a
    # chapter that loses precision silently is one nobody thinks to check.
    for parent, kids in _siblings(r["clause_id"] for r in rows).items():
        missing = [n for n in range(1, max(kids)) if n not in kids]
        if missing:
            report.append(f"  {chapter}: {parent} skips "
                          f"{[f'{parent}.{n}' for n in missing][:6]}"
                          f"{' ...' if len(missing) > 6 else ''} — those clauses "
                          f"are carried by {parent} itself, not lost")

    barren = sorted({r["clause_id"] for r in rows if r["status"] == "empty"})
    if barren:
        report.append(f"  {chapter}: {len(barren)} leaf clause(s) empty with no plan "
                      f"change to explain it: {barren[:6]}")
    held = sorted({r["clause_id"] for r in rows
                   if r["status"] == "replaced_by_plan_change"})
    if held:
        report.append(f"  {chapter}: {len(held)} clause(s) awaiting plan-change text "
                      f"(marked, not dropped): {held}")
    return rows


def main():
    index_file = PLAN / "plan_index.json"
    if not index_file.exists():
        sys.exit(f"{index_file} not found — run scripts/fetch_plan.py first")
    index = json.loads(index_file.read_text())
    if not DB.exists():
        sys.exit(f"{DB} not found — run scripts/build_db.py first")

    report, rows = [], []
    for ch in index["chapters"]:
        pdf = PLAN / ch["file"]
        got = chapter_clauses(pdf, ch["clause"], report)
        for r in got:
            r["zone_codes"] = ch["zone_codes"]
            r["excluded_zone_codes"] = ch.get("excluded_zone_codes") or []
            r["source_url"] = ch["url"]
        rows.extend(got)
        print(f"  {ch['clause']:<4} {len(got):>3} chunks  {ch['title']}")

    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false;")
    con.execute("""
        CREATE OR REPLACE TABLE plan_clause (
            clause_key TEXT PRIMARY KEY,   -- H5.6.4#1
            chapter TEXT, clause_id TEXT, title TEXT, part INTEGER,
            page_from INTEGER, page_to INTEGER,
            plan_changes TEXT[], zone_codes INTEGER[],
            excluded_zone_codes INTEGER[], status TEXT,
            source_url TEXT, text TEXT, chars INTEGER);
    """)
    con.executemany(
        "INSERT INTO plan_clause VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(f"{r['clause_id']}#{r['part']}", r["chapter"], r["clause_id"], r["title"],
          r["part"], r["page_from"], r["page_to"], r["plan_changes"],
          r["zone_codes"], r["excluded_zone_codes"], r["status"], r["source_url"],
          r["text"], len(r["text"]))
         for r in rows])

    # The mapping is only worth anything if both sides agree it exists. A zone
    # code with no chapter is a question the agent will have to refuse; a
    # chapter pointing at a code the zone layer never uses is a typo above.
    known = {c[0] for c in con.execute(
        "SELECT DISTINCT zone_code FROM planning_zone_ref").fetchall()}
    claimed = {z for ch in index["chapters"] for z in ch["zone_codes"]}
    if claimed - known:
        report.append(f"  chapters claim zone codes the zone layer does not have: "
                      f"{sorted(claimed - known)}")

    covered = con.execute(f"""
        SELECT count(*) FROM rating_unit
        WHERE planning_zone_code IN ({','.join(str(z) for z in claimed) or 'NULL'})
    """).fetchone()[0]
    total = con.execute("SELECT count(*) FROM rating_unit").fetchone()[0]
    con.execute("CHECKPOINT")
    con.close()

    out = DATA / "plan_report.txt"
    out.write_text(
        "Auckland Unitary Plan — clause extraction\n"
        f"source: {index['source']}\n\n"
        f"{len(index['chapters'])} chapters -> {len(rows)} chunks\n"
        f"parcels covered by a zone chapter: {covered:,} / {total:,} "
        f"({covered / total:.0%})\n\n"
        + ("anomalies:\n" + "\n".join(report) if report else "anomalies: none")
        + "\n", encoding="utf-8")

    print(f"\n{len(rows)} clause chunks -> plan_clause")
    print(f"parcels covered: {covered:,} / {total:,} ({covered / total:.0%})")
    print(f"report -> {out}")
    for line in report:
        print(line, file=sys.stderr)


if __name__ == "__main__":
    main()
