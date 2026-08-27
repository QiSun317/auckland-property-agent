from __future__ import annotations

import unittest

from fixtures import FIELDS, ROWS

from dataset import (
    aggregate_rows,
    calculate_project_numbers,
    clean_dataset,
    dataset_definition_facts,
    query_rows,
)


class DatasetTests(unittest.TestCase):
    def test_allow_list_zone_normalisation_and_filtering(self) -> None:
        dataset = clean_dataset({"fields": [*FIELDS, "secret"], "rows": ROWS})
        result = query_rows(
            dataset,
            {
                "numeric": [{"field": "entry_price", "max": 700000}],
                "sortBy": "gross_yield_pct",
                "direction": "desc",
                "limit": 5,
            },
        )
        self.assertEqual(len(dataset.rows), 2)
        self.assertEqual(dataset.rows[0]["zone"], "北岸")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["name"], "Beta Hills")
        self.assertNotIn("secret", result["rows"][0])

    def test_traceable_aggregate_facts(self) -> None:
        result = aggregate_rows(
            clean_dataset({"fields": FIELDS, "rows": ROWS}),
            {},
            "entry_price",
            "median",
            False,
        )
        self.assertEqual(
            result["data"],
            [{"group": "all", "matched": 2, "value": 725000.0, "suburb": None}],
        )
        self.assertEqual(
            result["facts"]["summary:all:entry_price:median:value"],
            725000.0,
        )

    def test_reusable_field_definition_facts(self) -> None:
        facts = dataset_definition_facts(
            clean_dataset({"fields": FIELDS, "rows": ROWS})
        )
        self.assertEqual(facts["constant:entry_price:percentile"], 25)
        self.assertIn(
            "25th-percentile",
            facts["constant:field:entry_price:definition"],
        )

    def test_deterministic_project_calculations(self) -> None:
        self.assertEqual(
            calculate_project_numbers("subtract", [800000, 650000]),
            150000,
        )
        self.assertEqual(
            calculate_project_numbers("percent_change", [650000, 800000]),
            23.08,
        )
        with self.assertRaisesRegex(ValueError, "zero"):
            calculate_project_numbers("divide", [1, 0])


if __name__ == "__main__":
    unittest.main()
