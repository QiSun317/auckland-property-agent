from __future__ import annotations

import unittest

from boundary import (
    clean_history,
    cors_headers,
    is_obviously_off_topic,
    safe_error,
)


class BoundaryTests(unittest.TestCase):
    def test_cors_origin_allow_list(self) -> None:
        allowed = "https://qisun317.github.io"
        self.assertEqual(
            cors_headers(allowed, allowed)["access-control-allow-origin"],
            allowed,
        )
        self.assertEqual(
            cors_headers("https://example.com", allowed)["access-control-allow-origin"],
            "null",
        )

    def test_history_is_bounded_and_cleaned(self) -> None:
        history = [
            {"role": "system", "content": "ignored"},
            *[{"role": "user", "content": f" turn {index} "} for index in range(10)],
        ]
        cleaned = clean_history(history)
        self.assertEqual(len(cleaned), 8)
        self.assertEqual(cleaned[0]["content"], "turn 2")

    def test_obvious_off_topic_is_declined(self) -> None:
        self.assertTrue(is_obviously_off_topic("请写一首诗"))
        self.assertFalse(is_obviously_off_topic("比较奥克兰房价"))
        self.assertFalse(
            is_obviously_off_topic(
                "What is the building height limit in the Mixed Housing Urban Zone?"
            )
        )

    def test_errors_redact_api_keys(self) -> None:
        key = "AIza0123456789abcdefghijkl"
        self.assertNotIn(key, safe_error(ValueError(f"key={key}")))


if __name__ == "__main__":
    unittest.main()
