from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from fixtures import FIELDS, ROWS
from langchain_core.messages import AIMessage

from agent import (
    _conversation_prompt,
    _run_tool_agent,
    _validate_response_language,
    detect_response_language,
    run_dataset_agent,
)
from dataset import clean_dataset


class FakePlanningRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    async def search(
        self, question: str, chapters: tuple[str, ...], limit: int
    ) -> list[dict[str, Any]]:
        self.calls.append((question, chapters, limit))
        return [
            {
                "id": "H5.6.4#1",
                "clause_key": "H5.6.4#1",
                "chapter": "H5",
                "clause_id": "H5.6.4",
                "title": "Building height",
                "page_from": 42,
                "page_to": 42,
                "plan_changes": "",
                "status": "ok",
                "source_url": "https://example.test/H5.pdf",
                "text": "Buildings must not exceed 11m in height.",
                "score": 0.91,
            }
        ]


class ScriptedModel:
    max_model_calls = 5

    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = responses
        self.bound_names: list[str] = []

    def bind_tools(self, tools: list[Any]) -> ScriptedModel:
        self.bound_names = [
            str(tool.get("name")) if isinstance(tool, dict) else tool.name
            for tool in tools
        ]
        return self

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return self.responses.pop(0)


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_plan_scope_is_deterministic_and_does_not_call_model(
        self,
    ) -> None:
        retriever = FakePlanningRetriever()
        with patch(
            "agent.GeminiWorkerChatModel",
            side_effect=AssertionError("model should not be called"),
        ):
            result = await run_dataset_agent(
                "unused",
                "unused",
                clean_dataset({"fields": FIELDS, "rows": ROWS}),
                text="How tall can I build in Remuera?",
                context="",
                history=[],
                planning_retriever=retriever,
            )

        self.assertIn("cannot infer", result["answer"])
        self.assertIn("exact planning-zone name", result["answer"])
        self.assertEqual(result["picks"], [])
        self.assertEqual(retriever.calls, [])
        self.assertEqual(len(result["evidence"]), 2)

    async def test_explicit_plan_zone_uses_grounded_langchain_tool(self) -> None:
        retriever = FakePlanningRetriever()
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submit_grounded_response",
                            "args": {
                                "on_topic": True,
                                "answer": (
                                    "项目保存的 H5.6.4 条款写明建筑高度不得超过 11m。"
                                    "这只是项目数据摘要，不是法律或许可意见。"
                                ),
                                "picks": [],
                                "citations": [
                                    "plan:H5.6.4#1:text",
                                    "plan:H5.6.4#1:source_url",
                                ],
                                "limitations": ["具体地块仍需核对叠加层及许可要求"],
                            },
                            "id": "final-plan",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        )

        result = await _run_tool_agent(
            model,
            clean_dataset({"fields": FIELDS, "rows": ROWS}),
            "Mixed Housing Urban 区能建多高？",
            "Chinese",
            retriever,
            current_question="Mixed Housing Urban 区能建多高？",
        )

        self.assertIn("search_unitary_plan", model.bound_names)
        self.assertEqual(
            retriever.calls,
            [
                (
                    "Mixed Housing Urban 区能建多高？",
                    ("E36", "E38", "H5"),
                    5,
                )
            ],
        )
        self.assertEqual(result["picks"], [])
        self.assertIn("H5.6.4", result["answer"])
        self.assertEqual(len(result["evidence"]), 2)

    async def test_tool_result_is_grounded_before_return(self) -> None:
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "lookup_suburbs",
                            "args": {"names": ["Alpha Bay", "Beta Hills"]},
                            "id": "lookup-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submit_grounded_response",
                            "args": {
                                "on_topic": True,
                                "answer": (
                                    "Beta Hills 的项目入门值为 $650,000，"
                                    "低于 Alpha Bay 的 $800,000。"
                                ),
                                "picks": [
                                    {
                                        "name": "Beta Hills",
                                        "why": "项目入门值为 $650,000，较低。",
                                    }
                                ],
                                "citations": [
                                    "suburb:Alpha Bay:entry_price",
                                    "suburb:Beta Hills:entry_price",
                                ],
                                "limitations": [],
                            },
                            "id": "final-1",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        )
        result = await _run_tool_agent(
            model,
            clean_dataset({"fields": FIELDS, "rows": ROWS}),
            "比较两个地区的入门值",
            "Chinese",
        )
        self.assertIn("submit_grounded_response", model.bound_names)
        self.assertEqual(result["picks"][0]["name"], "Beta Hills")
        self.assertEqual(
            {item["label"] for item in result["evidence"]},
            {
                "suburb:Alpha Bay:entry_price",
                "suburb:Beta Hills:entry_price",
            },
        )

    async def test_wrong_language_is_returned_to_model_for_repair(self) -> None:
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "lookup_suburbs",
                            "args": {"names": ["Beta Hills"]},
                            "id": "lookup-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submit_grounded_response",
                            "args": {
                                "on_topic": True,
                                "answer": "Beta Hills 的项目入门值是 $650,000。",
                                "picks": [],
                                "citations": ["suburb:Beta Hills:entry_price"],
                                "limitations": [],
                            },
                            "id": "wrong-language",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submit_grounded_response",
                            "args": {
                                "on_topic": True,
                                "answer": (
                                    "Beta Hills has a project entry value of $650,000."
                                ),
                                "picks": [],
                                "citations": ["suburb:Beta Hills:entry_price"],
                                "limitations": [],
                            },
                            "id": "corrected-language",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        )

        result = await _run_tool_agent(
            model,
            clean_dataset({"fields": FIELDS, "rows": ROWS}),
            "Required response language: English.\n\nCurrent user question:\n"
            "What is the entry value for Beta Hills?",
            "English",
        )

        self.assertEqual(
            result["answer"], "Beta Hills has a project entry value of $650,000."
        )


class AgentLanguageTests(unittest.TestCase):
    def test_current_english_question_overrides_chinese_context(self) -> None:
        question = "Which Auckland suburb has the lowest entry price?"
        language = detect_response_language(question)
        prompt = _conversation_prompt(
            question,
            "预算 100 万，三房",
            [{"role": "assistant", "content": "可以考虑南区。"}],
            language,
        )

        self.assertEqual(language, "English")
        self.assertTrue(prompt.startswith("Required response language: English."))
        self.assertIn(f"Current user question:\n{question}", prompt)

    def test_mixed_question_with_chinese_uses_chinese(self) -> None:
        self.assertEqual(detect_response_language("Papakura 的入门值是多少？"), "Chinese")

    def test_english_response_rejects_reader_facing_chinese(self) -> None:
        with self.assertRaisesRegex(ValueError, "entirely in English"):
            _validate_response_language(
                {
                    "answer": "Papakura 的 entry price is lower.",
                    "picks": [],
                    "limitations": [],
                },
                "English",
            )

    def test_english_response_accepts_english(self) -> None:
        _validate_response_language(
            {
                "answer": "Papakura has the lower project entry value.",
                "picks": [{"name": "Papakura", "why": "It has the lower value."}],
                "limitations": [],
            },
            "English",
        )


if __name__ == "__main__":
    unittest.main()
