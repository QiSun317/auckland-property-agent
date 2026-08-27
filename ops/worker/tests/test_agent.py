from __future__ import annotations

import unittest
from typing import Any

from fixtures import FIELDS, ROWS
from langchain_core.messages import AIMessage

from agent import _run_tool_agent
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


if __name__ == "__main__":
    unittest.main()
