import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pipeline


class ArtifactTest(unittest.TestCase):
    def test_incomplete_nested_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            index = raw / "plan" / "plan_index.json"
            index.parent.mkdir()
            index.write_text("{}")
            source = types.SimpleNamespace(
                artifact="plan/plan_index.json",
                check=lambda path, state: (_ for _ in ()).throw(
                    pipeline.Reject("H1.pdf missing")))

            with patch.object(pipeline, "RAW", raw):
                self.assertTrue(pipeline.artifact_missing(source, {}))


if __name__ == "__main__":
    unittest.main()
