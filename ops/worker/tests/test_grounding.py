from __future__ import annotations

import unittest

from fixtures import FIELDS, ROWS

from dataset import clean_dataset
from grounding import ground_agent_response


class GroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = clean_dataset({"fields": FIELDS, "rows": ROWS})
        self.facts = {
            "suburb:Alpha Bay:entry_price": 800000,
            "suburb:Alpha Bay:zone": "北岸",
        }

    def test_accepts_exact_citations_and_known_picks(self) -> None:
        result = ground_agent_response(
            {
                "on_topic": True,
                "answer": "Alpha Bay 的项目入门值是 **$800,000** [suburb:Alpha Bay:entry_price]。",
                "picks": [{"name": "Alpha Bay", "why": "项目把它归在北岸。"}],
                "citations": [
                    "suburb:Alpha Bay:entry_price",
                    "suburb:Alpha Bay:zone",
                ],
                "limitations": [],
            },
            self.dataset,
            self.facts,
        )
        self.assertEqual(result["picks"][0]["name"], "Alpha Bay")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["answer"], "Alpha Bay 的项目入门值是 $800,000。")

    def test_rejects_uncited_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "Uncited numeric claim"):
            ground_agent_response(
                {
                    "on_topic": True,
                    "answer": "Alpha Bay 距离市中心 9km。",
                    "picks": [],
                    "citations": ["suburb:Alpha Bay:zone"],
                    "limitations": [],
                },
                self.dataset,
                self.facts,
            )

    def test_attaches_exact_fact_when_label_is_omitted(self) -> None:
        result = ground_agent_response(
            {
                "on_topic": True,
                "answer": "项目的入门值口径是 25%。",
                "picks": [],
                "citations": [],
                "limitations": [],
            },
            self.dataset,
            {"constant:entry_price:percentile": 25},
        )
        self.assertEqual(
            result["evidence"],
            [{"label": "constant:entry_price:percentile", "value": 25}],
        )

    def test_explicit_limitation_needs_no_invented_evidence(self) -> None:
        result = ground_agent_response(
            {
                "on_topic": True,
                "answer": "项目数据没有学校质量字段，因此不能据此比较。",
                "picks": [],
                "citations": [],
                "limitations": ["项目数据不含学校质量"],
            },
            self.dataset,
            {},
        )
        self.assertEqual(len(result["limitations"]), 1)


if __name__ == "__main__":
    unittest.main()
