#!/usr/bin/env python3
"""Read what the suburb intros say, once, and turn it into fields.

Seventy percent of what the assistant sends the model is 69 KB of Wikipedia
opening paragraphs, and almost none of it is reachable by anything except the
model. Ask for somewhere near the beach and the rules had exactly one keyword
test to work with; ask for bush or a town centre and they had nothing, so the
answer quietly came back scored on everything except the thing that was asked.

This extracts the traits at build time instead. Doing it here rather than at
query time is the whole point: 205 rows can be read and spot-checked by a
person, a retrieval result cannot, and the extraction runs once instead of on
every question.

Three rules make the output trustworthy:

  * Tri-state, never false. A trait is true or unknown. Wikipedia not
    mentioning a beach is not evidence there is no beach, and an absent value
    has to keep saying "nobody said" rather than hardening into "no".
  * Every true carries its evidence — the phrase in the source that justified
    it. Nothing is asserted that cannot be pointed at.
  * Nothing is extracted that a reliable field already answers. An island
    trait read from prose scored twelve suburbs and six of them were wrong —
    a ferry departing *to* an island, a marine reserve named after one, a
    sandbar that becomes one at high tide. The local board boundaries already
    say which six suburbs are on Waiheke, exactly and without reading anything.

  * A match inside a "formerly / originally / no longer" clause is rejected.
    Kelston reads "Originally a ceramics manufacturing centre, the area is now
    mostly residential", and a reader of that sentence does not conclude the
    place is industrial.

    python3 scripts/suburb_traits.py            # extract and report coverage
    python3 scripts/suburb_traits.py --show coastal
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AKL_ROOT", Path(__file__).resolve().parent.parent))
RAW = Path(os.environ.get("AKL_RAW_DIR", ROOT / "data" / "raw"))

# Words that turn a statement into a statement about the past. Checked in the
# run-up to a match, not the whole text: "formerly rural, now a suburb" must
# reject rural, while "a rural area near the formerly industrial port" must not
# reject rural.
# Widened after reading the misses. "was a" was too literal: the corpus says
# "was largely a dairy farming area", "was developed into orchards", and
# "Established as a rural community in the 1850s" — all plainly about the past,
# none of them matching. A bare "was/were" plus the founding formulas covers
# them, at the cost of occasionally rejecting a present state described in the
# past tense, which is the safer way to be wrong.
PAST = re.compile(r"\b(originally|formerly|once|previously|used to|no longer|"
                  r"until the|historically|in the past|was|were|had been|"
                  r"established as|founded|settled|developed into|"
                  r"during the|in the (17|18|19)\d\d)\b[^.;]{0,60}$", re.I)

# Being near a thing is not being the thing. "To the east lies the islands of
# Rangitoto" was making Castor Bay an island suburb, and "north of the Hunua
# Ranges" was making Kawakawa Bay bush. Applied only to traits where proximity
# genuinely does not count — for coastal it does, since "close to the waters of
# the Tāmaki River estuary" is exactly what being coastal means here.
NEARBY = re.compile(r"\b(north|south|east|west|northeast|northwest|southeast|"
                    r"southwest) of\b[^.;]{0,50}$|"
                    r"\b(near|close to|views? of|overlooking|opposite|across from|"
                    r"adjacent to|lies|beyond|towards?|facing)\b[^.;]{0,50}$", re.I)
PROXIMITY_MATTERS = {"coastal", "volcanic", "town_centre"}

# Where the suburb's own name was, so a word right after it can be recognised
# as the tail of a compound name. Only consulted for the strict traits: a beach
# called "<Name> Beach" really is the suburb's beach, but a shopping strip
# called "<Name> Village" is not countryside.
NAME_SLOT = "\u2e24\u2e25"
COMPOUND = re.compile(re.escape(NAME_SLOT) + r"\W{0,3}$")

# Wikipedia openers often carry a pronunciation gloss, and a hyphen is a word
# boundary: "Devonport ( DEV-ən-port)" put the token "port" in the text and made
# a harbourside suburb industrial. Strip anything parenthetical that looks like
# phonetics before matching a single pattern against it.
PRONUNCIATION = re.compile(r"\([^)]*[əˈˌːɑɛɪɔʊθðʃʒŋæ\u0361][^)]*\)")

# Proper nouns that contain a trait word without being about the place. The
# Auckland Harbour Bridge made Glenfield coastal; the same shape as "the North
# Shore" and "the North Island" before it. Three of these turned up in one
# corpus, which is a fair warning that there are more.
PROPER_NOUNS = re.compile(r"\bAuckland Harbou?r Bridge\b|\bHarbou?r Bridge\b|"
                          r"\bNorth Shore (City|Hospital)\b", re.I)

# Each trait is a list of patterns. Written against the real corpus, not from
# imagination — every one of these fires on at least one actual intro.
TRAITS = {
    "coastal": [
        r"\bbeach(es|side|front)?\b", r"\bcoast(al|line)?\b",
        # "the North Shore" is a region, the way "the North Island" is — it
        # named 28 suburbs coastal on the strength of an address. Suburbs that
        # are genuinely on the water say so some other way in the same sentence,
        # and the loop finds that instead.
        r"(?<!north )(?<!the north )\bshores?\b",
        r"\bharbou?r\b", r"\bwaterfront\b", r"\bseaside\b",
        r"\bestuary\b", r"\bgulf\b", r"\bpeninsulas?\b", r"\binlet\b",
        r"\bfronts the\b", r"\btidal\b",
    ],
    "bush": [
        r"\bforest(ed)?\b", r"\bbush(land|-clad)?\b",
        r"\bnative (bush|forest)\b", r"\brainforest\b",
        r"\bWait[āa]kere Ranges\b", r"\bHunua Ranges\b", r"\bscenic reserve\b",
    ],
    "rural": [
        r"\brural\b", r"\bfarmland\b", r"\bfarming\b", r"\bcountryside\b",
        r"\bsmall town\b", r"\bvillage(?! centre)\b", r"\btownship\b",
        r"\borchards?\b",
        r"\blifestyle blocks?\b",
    ],
    "volcanic": [
        r"\bvolcan(o|oes|ic)\b", r"\bmaunga\b", r"\bcrater\b", r"\bscoria\b",
        r"\bcinder cone\b", r"\blava\b", r"\btuff ring\b",
    ],
    # A distance reference — "4 km from the Auckland City Centre" — is not the
    # suburb having a centre of its own, so the bare phrase cannot be enough.
    "town_centre": [
        r"\b(town|shopping|commercial|retail|civic) (centre|center)\b",
        r"\bshopping (mall|precinct)\b", r"\bmain street\b",
        r"\bbusiness (district|area)\b", r"\bcommercial (hub|precinct)\b",
    ],
    "historic": [
        r"\bhistoric(al)?\b", r"\bheritage\b", r"\boldest\b", r"\bVictorian\b",
        r"\bcolonial\b", r"\bestablished in 1[89]\d\d\b",
        r"\bsettled in 1[89]\d\d\b", r"\bfounded in 1[89]\d\d\b",
    ],
    "industrial": [
        r"\bindustrial\b", r"\bindustry\b", r"\bmanufacturing\b",
        r"\bwarehous(e|ing|es)\b", r"\bfactor(y|ies)\b", r"\bport\b",
        r"\bquarry\b",
    ],
}

LABELS = {
    "coastal": ("近海", "coastal"), "bush": ("近林地", "bush"),
    "rural": ("乡村", "rural"), "island": ("海岛", "island"),
    "volcanic": ("火山地貌", "volcanic"), "town_centre": ("有商业中心", "town centre"),
    "historic": ("历史街区", "historic"), "industrial": ("有工业", "industrial"),
}


def evidence(text, m):
    """The phrase a reader would point at. Enough context to judge it, short
    enough to show."""
    a, b = max(0, m.start() - 34), min(len(text), m.end() + 34)
    return ("…" if a else "") + text[a:b].strip().replace("\n", " ") + ("…" if b < len(text) else "")


def traits_for(text, name=None):
    """Tri-state. A trait is present with its evidence, or absent entirely."""
    if not text:
        return {}
    text = PRONUNCIATION.sub(" ", text)
    text = PROPER_NOUNS.sub(" ", text)
    # A suburb called Flat Bush is not thereby bushy. Blank the name out — but
    # leave a marker rather than spaces, because the name is often the first
    # half of a compound proper noun. Blanking "Sandringham" out of
    # "Sandringham Village" left a bare "Village" that read as countryside, so
    # the fix for one problem created the next one.
    if name:
        text = re.sub(re.escape(name), NAME_SLOT, text, flags=re.I)

    out = {}
    for trait, pats in TRAITS.items():
        strict = trait not in PROXIMITY_MATTERS
        for p in pats:
            for m in re.finditer(p, text, re.I):
                lead = text[:m.start()]
                if PAST.search(lead):
                    continue                      # a statement about the past
                if strict and NEARBY.search(lead):
                    continue                      # near it, not it
                if strict and COMPOUND.search(lead):
                    continue                      # the tail of the place's own name
                out[trait] = evidence(text, m)
                break
            if trait in out:
                break
    return out


def extract_all():
    wiki = json.loads((RAW / "wikipedia.json").read_text())
    return {name: traits_for((v or {}).get("extract") or "", name)
            for name, v in wiki.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", metavar="TRAIT", help="every suburb with this trait, and why")
    a = ap.parse_args()

    wiki = json.loads((RAW / "wikipedia.json").read_text())
    got = extract_all()
    n = len([1 for v in wiki.values() if (v or {}).get("extract")])

    if a.show:
        if a.show not in TRAITS:
            sys.exit(f"unknown trait {a.show!r} — one of {', '.join(TRAITS)}")
        hits = sorted((k, v[a.show]) for k, v in got.items() if a.show in v)
        print(f"{len(hits)} suburbs where the intro says {a.show}\n")
        for name, why in hits:
            print(f"  {name}\n      {why}")
        return

    print(f"{n} intros read\n")
    print(f"{'trait':<14}{'found':>7}{'share':>8}   example")
    for t in TRAITS:
        hits = [(k, v[t]) for k, v in got.items() if t in v]
        ex = hits[0][0] if hits else "—"
        print(f"  {t:<12}{len(hits):>7}{len(hits) / n * 100:>7.0f}%   {ex}")

    none = [k for k, v in got.items() if not v]
    print(f"\n  {len(none)} intros yielded nothing at all "
          f"({len(none) / n * 100:.0f}%) — mostly one-liners")
    print(f"  e.g. {', '.join(sorted(none)[:6])}")


if __name__ == "__main__":
    main()
