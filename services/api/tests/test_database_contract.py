from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scholarflow_api.database import get_connection


class DatabaseContractTest(unittest.TestCase):
    def test_every_new_connection_enables_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scholarflow.sqlite3"
            with patch.dict(os.environ, {"SCHOLARFLOW_DB_PATH": str(db_path)}):
                with get_connection() as connection:
                    foreign_keys = connection.execute(
                        "PRAGMA foreign_keys",
                    ).fetchone()[0]

        self.assertEqual(foreign_keys, 1)


if __name__ == "__main__":
    unittest.main()
