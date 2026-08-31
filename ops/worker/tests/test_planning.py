from __future__ import annotations

import json
import unittest

from dataset import clean_dataset
from fixtures import FIELDS, ROWS
from planning import (
    CloudflarePlanningRetriever,
    explicit_plan_scope,
    facts_for_plan_hits,
)
from tools import create_dataset_tools


class FakeAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, model: str, payload: dict) -> dict:
        self.calls.append((model, payload))
        return {"data": [[0.25] * 1024]}


class FakeIndex:
    def __init__(self, chapter: str = "H5") -> None:
        self.chapter = chapter
        self.calls: list[tuple[list[float], dict]] = []

    async def query(self, vector: list[float], options: dict) -> dict:
        self.calls.append((vector, options))
        return {
            "matches": [
                {
                    "id": "H5.6.4#1",
                    "score": 0.91,
                    "metadata": {
                        "clause_key": "H5.6.4#1",
                        "chapter": self.chapter,
                        "clause_id": "H5.6.4",
                        "title": "Building height",
                        "page_from": 42,
                        "page_to": 42,
                        "plan_changes": "",
                        "status": "ok",
                        "source_url": "https://example.test/H5.pdf",
                        "text": "Buildings must not exceed 11m in height.",
                    },
                }
            ]
        }


class PlanScopeTests(unittest.TestCase):
    def test_resolves_full_zone_name_and_abbreviation(self) -> None:
        full = explicit_plan_scope(
            "How tall in the Residential - Mixed Housing Urban Zone?"
        )
        short = explicit_plan_scope("MHU 能建多高？")
        self.assertIsNotNone(full)
        self.assertEqual(full.code, 60)
        self.assertEqual(full.chapters, ("E36", "E38", "H5"))
        self.assertEqual(short, full)

    def test_resolves_explicit_code_or_chapter(self) -> None:
        by_code = explicit_plan_scope("What applies in planning zone code 60?")
        by_chapter = explicit_plan_scope("H19 的建筑高度规则是什么？")
        self.assertEqual(by_code.code, 60)
        self.assertEqual(by_chapter.chapters, ("E36", "E39", "H19"))

    def test_does_not_infer_zone_from_suburb(self) -> None:
        self.assertIsNone(explicit_plan_scope("How tall can I build in Remuera?"))

    def test_rejects_multiple_scopes(self) -> None:
        with self.assertRaisesRegex(ValueError, "multiple planning-zone scopes"):
            explicit_plan_scope("Compare H4 with H5")


class PlanningRetrieverTests(unittest.IsolatedAsyncioTestCase):
    async def test_workers_ai_query_is_filtered_before_vector_search(self) -> None:
        ai = FakeAI()
        index = FakeIndex()
        retriever = CloudflarePlanningRetriever(ai, index)

        hits = await retriever.search(
            "how tall can I build", ("E36", "E38", "H5"), 5
        )

        self.assertEqual(ai.calls[0][0], "@cf/baai/bge-m3")
        self.assertEqual(len(index.calls[0][0]), 1024)
        self.assertEqual(
            index.calls[0][1]["filter"],
            {"chapter": {"$in": ["E36", "E38", "H5"]}},
        )
        self.assertEqual(hits[0]["clause_key"], "H5.6.4#1")

    async def test_rejects_binding_result_outside_scope(self) -> None:
        retriever = CloudflarePlanningRetriever(FakeAI(), FakeIndex(chapter="H4"))
        with self.assertRaisesRegex(RuntimeError, "outside the filtered scope"):
            await retriever.search("height", ("E36", "E38", "H5"), 5)

    async def test_langchain_tool_enforces_current_question_scope(self) -> None:
        dataset = clean_dataset({"fields": FIELDS, "rows": ROWS})
        retriever = CloudflarePlanningRetriever(FakeAI(), FakeIndex())
        tools, _ = create_dataset_tools(
            dataset,
            retriever,
            current_question="How tall in the Mixed Housing Urban Zone?",
        )
        search = next(tool for tool in tools if tool.name == "search_unitary_plan")
        result = json.loads(
            await search.ainvoke({"question": "building height", "limit": 5})
        )

        self.assertEqual(result["data"]["scope"]["code"], 60)
        self.assertIn("plan:H5.6.4#1:text", result["facts"])

        unsafe_tools, _ = create_dataset_tools(
            dataset,
            retriever,
            current_question="How tall can I build in Remuera?",
        )
        unsafe_search = next(
            tool for tool in unsafe_tools if tool.name == "search_unitary_plan"
        )
        with self.assertRaisesRegex(ValueError, "does not state an exact"):
            await unsafe_search.ainvoke({"question": "building height"})

    def test_plan_hit_facts_are_citable(self) -> None:
        facts = facts_for_plan_hits(
            [
                {
                    "clause_key": "H5.6.4#1",
                    "text": "Buildings must not exceed 11m.",
                    "page_from": 42,
                    "score": 0.91,
                }
            ]
        )
        self.assertEqual(
            facts["plan:H5.6.4#1:text"], "Buildings must not exceed 11m."
        )
        self.assertEqual(facts["plan:H5.6.4#1:page_from"], 42)


if __name__ == "__main__":
    unittest.main()
