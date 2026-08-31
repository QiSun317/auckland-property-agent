"""Exact-zone Unitary Plan retrieval over Workers AI and Vectorize."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

EMBEDDING_MODEL = "@cf/baai/bge-m3"
EMBEDDING_DIMENSIONS = 1024

# Generated from planning_zone_ref + plan_clause applicability in the project
# database. The online Worker deliberately carries only this compact routing
# map; clause text and vectors remain in Vectorize.
PLAN_ZONES: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Business - Business Park Zone", ("E36", "E38", "H15")),
    3: ("Rural - Countryside Living Zone", ("E36", "E39", "H19")),
    4: ("Future Urban Zone", ("E36", "E39", "H18")),
    5: ("Business - Heavy Industry Zone", ("E36", "E38", "H16")),
    7: ("Business - Local Centre Zone", ("E36", "E38", "H11")),
    8: (
        "Residential - Terrace Housing and Apartment Building Zone",
        ("E36", "E38", "H6"),
    ),
    10: ("Business - Metropolitan Centre Zone", ("E36", "E38", "H9")),
    11: ("Rural - Mixed Rural Zone", ("E36", "E39", "H19")),
    12: ("Business - Mixed Use Zone", ("E36", "E38", "H13")),
    15: ("Rural - Rural Conservation Zone", ("E36", "E39", "H19")),
    16: ("Rural - Rural Production Zone", ("E36", "E39", "H19")),
    17: ("Business - Light Industry Zone", ("E36", "E38", "H17")),
    18: (
        "Residential - Mixed Housing Suburban Zone",
        ("E36", "E38", "H4"),
    ),
    19: ("Residential - Single House Zone", ("E36", "E38", "H3")),
    20: (
        "Residential - Rural and Coastal Settlement Zone",
        ("E36", "E38", "H2"),
    ),
    22: ("Business - Town Centre Zone", ("E36", "E38", "H10")),
    23: ("Residential - Large Lot Zone", ("E36", "E38", "H1")),
    25: ("Water", ("E36", "E38")),
    26: ("Strategic Transport Corridor Zone", ("E36", "E38")),
    27: ("Road", ("E36", "E38")),
    30: ("Coastal - General Coastal Marine Zone", ("E36", "E38")),
    31: ("Open Space - Conservation Zone", ("E36", "E38", "H7")),
    32: ("Open Space - Informal Recreation Zone", ("E36", "E38", "H7")),
    33: (
        "Open Space - Sport and Active Recreation Zone",
        ("E36", "E38", "H7"),
    ),
    34: ("Open Space - Community Zone", ("E36", "E38", "H7")),
    35: ("Business - City Centre Zone", ("E36", "E38", "H8")),
    37: ("Coastal - Minor Port Zone", ("E36", "E38")),
    39: ("Coastal - Defence Zone", ("E36", "E38")),
    40: ("Coastal - Marina Zone", ("E36", "E38")),
    41: ("Coastal - Mooring Zone", ("E36", "E38")),
    43: ("Hauraki Gulf Islands", ("E36", "E38")),
    44: ("Business - Neighbourhood Centre Zone", ("E36", "E38", "H12")),
    45: ("Coastal - Ferry Terminal Zone", ("E36", "E38")),
    46: ("Rural - Rural Coastal Zone", ("E36", "E39", "H19")),
    49: ("Business - General Business Zone", ("E36", "E38", "H14")),
    51: ("Special Purpose - Quarry Zone", ("E36", "E39")),
    52: ("Special Purpose - Māori Purpose Zone", ("E36", "E38")),
    53: ("Special Purpose - Cemetery Zone", ("E36", "E38")),
    54: (
        "Special Purpose - Major Recreation Facility Zone",
        ("E36", "E38"),
    ),
    55: (
        "Special Purpose - Healthcare Facility and Hospital Zone",
        ("E36", "E38"),
    ),
    56: ("Special Purpose - Airports and Airfields Zone", ("E36", "E38")),
    59: ("Coastal - Coastal Transition Zone", ("E36", "E38")),
    60: ("Residential - Mixed Housing Urban Zone", ("E36", "E38", "H5")),
    61: ("Green Infrastructure Corridor", ("E36", "E38")),
    62: ("Open Space - Civic Spaces Zone", ("E36", "E38", "H7")),
    63: ("Special Purpose - School Zone", ("E36", "E38")),
    64: ("Special Purpose - Tertiary Education Zone", ("E36", "E38")),
    68: ("Rural - Waitakere Foothills Zone", ("E36", "E39", "H20")),
    69: ("Rural - Waitakere Ranges Zone", ("E36", "E39", "H21")),
}

ZONE_ABBREVIATIONS = {
    "mhu": 60,
    "mhs": 18,
    "shz": 19,
    "thab": 8,
}


@dataclass(frozen=True)
class PlanScope:
    code: int | None
    name: str
    chapters: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "name": self.name, "chapters": list(self.chapters)}


class PlanningRetriever(Protocol):
    async def search(
        self, question: str, chapters: tuple[str, ...], limit: int
    ) -> list[dict[str, Any]]: ...


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-–—]+", " ", value.casefold())).strip()


def _zone_aliases(name: str) -> set[str]:
    aliases = {_normalise(name)}
    short = name.split(" - ", 1)[-1]
    aliases.add(_normalise(short))
    if short.casefold().endswith(" zone"):
        aliases.add(_normalise(short[:-5]))
    return {alias for alias in aliases if alias}


def _chapter_scope(chapter: str) -> PlanScope:
    if chapter in {"E36", "E38", "E39"}:
        return PlanScope(None, f"Unitary Plan chapter {chapter}", (chapter,))
    number = int(chapter[1:])
    regionwide = "E39" if number >= 18 else "E38"
    return PlanScope(None, f"Unitary Plan chapter {chapter}", ("E36", regionwide, chapter))


def explicit_plan_scope(text: str) -> PlanScope | None:
    """Resolve only a zone/chapter literally present in the current question."""

    normalised = _normalise(text)
    candidates: dict[tuple[str, ...], PlanScope] = {}

    code_patterns = (
        r"\b(?:planning\s+)?zone(?:\s+code)?\s*[:#-]?\s*(\d{1,2})\b",
        r"(?:规划区|分区)(?:代码)?\s*[:#：-]?\s*(\d{1,2})",
    )
    for pattern in code_patterns:
        for match in re.finditer(pattern, normalised, re.IGNORECASE):
            code = int(match.group(1))
            if code in PLAN_ZONES:
                name, chapters = PLAN_ZONES[code]
                candidates[chapters] = PlanScope(code, name, chapters)

    for match in re.finditer(r"\b(H(?:[1-9]|1\d|2[01])|E(?:36|38|39))\b", text, re.IGNORECASE):
        scope = _chapter_scope(match.group(1).upper())
        candidates[scope.chapters] = scope

    for code, (name, chapters) in PLAN_ZONES.items():
        if any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalised)
            for alias in _zone_aliases(name)
        ):
            candidates[chapters] = PlanScope(code, name, chapters)

    for abbreviation, code in ZONE_ABBREVIATIONS.items():
        if re.search(rf"\b{abbreviation}\b", text, re.IGNORECASE):
            name, chapters = PLAN_ZONES[code]
            candidates[chapters] = PlanScope(code, name, chapters)

    if not candidates:
        return None
    if len(candidates) > 1:
        raise ValueError(
            "The current question names multiple planning-zone scopes; ask the user "
            "to choose one exact zone or chapter"
        )
    return next(iter(candidates.values()))


def planning_scope_facts() -> dict[str, str | int]:
    return {
        "constant:plan:source": (
            "Auckland Unitary Plan (Operative in Part) chapters stored by this project"
        ),
        "constant:plan:exact_zone_required": (
            "An individual property's planning zone must not be inferred from its suburb. "
            "The current question must state an exact zone name, zone code, or chapter."
        ),
        "constant:plan:zone_count": len(PLAN_ZONES),
    }


def planning_zones_for_tool() -> list[dict[str, Any]]:
    return [
        {"code": code, "name": name, "chapters": list(chapters)}
        for code, (name, chapters) in PLAN_ZONES.items()
    ]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _to_python(value: Any) -> Any:
    if hasattr(value, "to_py"):
        value = value.to_py()
    if isinstance(value, dict):
        return {str(key): _to_python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_python(item) for item in value]
    return value


class CloudflarePlanningRetriever:
    """Thin, request-scoped adapter around native Worker bindings."""

    def __init__(self, ai_binding: Any, vector_binding: Any) -> None:
        self.ai = ai_binding
        self.index = vector_binding

    async def search(
        self, question: str, chapters: tuple[str, ...], limit: int
    ) -> list[dict[str, Any]]:
        if not question.strip():
            raise ValueError("Plan search question is empty")
        if not 1 <= limit <= 8:
            raise ValueError("Plan search limit must be between 1 and 8")
        if not chapters:
            raise ValueError("Plan search requires a chapter scope")

        embedding_response = await self.ai.run(
            EMBEDDING_MODEL, {"text": [question.strip()[:800]]}
        )
        data = _field(embedding_response, "data")
        if data is None or len(data) != 1:
            raise RuntimeError("Workers AI returned no query embedding")
        vector = data[0]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Workers AI returned {len(vector)} dimensions; "
                f"expected {EMBEDDING_DIMENSIONS}"
            )

        response = await self.index.query(
            vector,
            {
                "topK": limit,
                "returnValues": False,
                "returnMetadata": "all",
                "filter": {"chapter": {"$in": list(chapters)}},
            },
        )
        raw_matches = _field(response, "matches", [])
        matches = _to_python(raw_matches)
        results: list[dict[str, Any]] = []
        for match in matches:
            metadata = _field(match, "metadata", {})
            if not isinstance(metadata, dict):
                continue
            chapter = str(metadata.get("chapter", ""))
            if chapter not in chapters:
                raise RuntimeError("Vectorize returned a clause outside the filtered scope")
            results.append(
                {
                    **metadata,
                    "id": str(_field(match, "id", metadata.get("clause_key", ""))),
                    "score": round(float(_field(match, "score", 0.0)), 6),
                }
            )
        return results


def facts_for_plan_hits(hits: list[dict[str, Any]]) -> dict[str, str | int | float]:
    facts: dict[str, str | int | float] = {}
    for hit in hits:
        clause_key = str(hit.get("clause_key") or hit.get("id") or "").strip()
        if not clause_key:
            continue
        prefix = f"plan:{clause_key}"
        for field in (
            "chapter",
            "clause_id",
            "title",
            "page_from",
            "page_to",
            "plan_changes",
            "status",
            "source_url",
            "text",
            "score",
        ):
            value = hit.get(field)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                facts[f"{prefix}:{field}"] = value
    return facts
