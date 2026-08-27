from __future__ import annotations

import unittest
from typing import Any

from fixtures import FIELDS, ROWS
from langchain_core.messages import AIMessage

from agent import (
    _conversation_prompt,
    _run_tool_agent,
    _validate_response_language,
    detect_response_language,
)
from dataset import clean_dataset


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
