import sys
import unittest
from pathlib import Path

from src.verification.process import run_command
from test_support import workspace_tempdir


class ProcessRunnerTests(unittest.TestCase):
    def test_captures_output_and_writes_log(self):
        with workspace_tempdir() as tmp:
            log_path = tmp / "tool.log"
            result = run_command(
                [sys.executable, "-c", "print('hello verification')"],
                timeout_seconds=2,
                log_path=log_path,
            )

            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.timed_out)
            self.assertIn("hello verification", result.output)
            self.assertIn("hello verification", log_path.read_text(encoding="utf-8"))

    def test_timeout_is_reported_without_being_not_equivalent(self):
        with workspace_tempdir() as tmp:
            log_path = tmp / "timeout.log"
            result = run_command(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                timeout_seconds=0.05,
                log_path=log_path,
            )

            self.assertTrue(result.timed_out)
            self.assertIsNone(result.returncode)
            self.assertTrue(log_path.exists())


if __name__ == "__main__":
    unittest.main()
