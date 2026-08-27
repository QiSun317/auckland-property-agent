from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent import FINAL_RESPONSE_TOOL
from gemini import _messages_to_gemini, _tool_declaration


class GeminiAdapterTests(unittest.TestCase):
    def test_parallel_tool_results_share_one_gemini_user_turn(self) -> None:
        raw_parts = [
            {
                "functionCall": {
                    "id": "call-1",
                    "name": "lookup_suburbs",
                    "args": {"names": ["Alpha Bay"]},
                },
                "thoughtSignature": "preserve-me",
            },
            {
                "functionCall": {
                    "id": "call-2",
                    "name": "describe_dataset",
                    "args": {},
                }
            },
        ]
        system, contents = _messages_to_gemini(
            [
                SystemMessage("rules"),
                HumanMessage("question"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "lookup_suburbs",
                            "args": {"names": ["Alpha Bay"]},
                            "id": "call-1",
                            "type": "tool_call",
                        },
                        {
                            "name": "describe_dataset",
                            "args": {},
                            "id": "call-2",
                            "type": "tool_call",
                        },
                    ],
                    additional_kwargs={"gemini_parts": raw_parts},
                ),
                ToolMessage(
                    content='{"data":{},"facts":{}}',
                    tool_call_id="call-1",
                    name="lookup_suburbs",
                ),
                ToolMessage(
                    content='{"data":{},"facts":{}}',
                    tool_call_id="call-2",
                    name="describe_dataset",
                ),
            ]
        )
        self.assertEqual(system, "rules")
        self.assertEqual(contents[1]["parts"], raw_parts)
        self.assertEqual(len(contents[2]["parts"]), 2)

    def test_final_tool_uses_json_schema(self) -> None:
        declaration = _tool_declaration(FINAL_RESPONSE_TOOL)
        self.assertEqual(declaration["name"], "submit_grounded_response")
        self.assertEqual(
            declaration["parametersJsonSchema"]["required"],
            ["on_topic", "answer", "picks", "citations", "limitations"],
        )


if __name__ == "__main__":
    unittest.main()
