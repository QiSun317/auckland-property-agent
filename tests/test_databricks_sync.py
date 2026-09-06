import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import databricks_sync


class BadRequest(Exception):
    pass


class Warehouses:
    def __init__(self):
        self.starts = 0

    def list(self):
        return [types.SimpleNamespace(id="warehouse-id", name="test", state="STOPPED")]

    def start(self, _warehouse_id):
        self.starts += 1
        return self

    def result(self, timeout):
        if self.starts < 3:
            raise BadRequest("Cannot create the resource, please try again later.")


class WarehouseTest(unittest.TestCase):
    def test_transient_start_failure_is_retried(self):
        warehouses = Warehouses()
        errors = types.ModuleType("databricks.sdk.errors")
        errors.BadRequest = BadRequest
        with patch.dict(sys.modules, {"databricks.sdk.errors": errors}), \
                patch.object(databricks_sync.time, "sleep") as sleep:
            databricks_sync.warehouse(types.SimpleNamespace(warehouses=warehouses))

        self.assertEqual(warehouses.starts, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [15, 30])


if __name__ == "__main__":
    unittest.main()
