import sys
import unittest
from pathlib import Path

from src.verification.api import verify
from src.verification.config import VerificationConfig
from test_support import workspace_tempdir


class VerificationApiValidationTests(unittest.TestCase):
    def test_missing_golden_file_is_an_error_with_metadata_and_null_equivalence(self):
        with workspace_tempdir() as tmp:
            result = verify(
                tmp / "missing.v",
                tmp / "candidate.v",
                VerificationConfig(run_dir=tmp / "run"),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "missing_file")
            self.assertFalse(result["is_mock"])
            self.assertIsNotNone(result["elapsed_seconds"])
            self.assertTrue(Path(result["log_path"]).exists())
            self.assertTrue((tmp / "run" / "run_metadata.json").exists())

    def test_invalid_mode_is_rejected_before_running_tools(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            golden.write_text("module top(input a, output y); assign y = a; endmodule\n", encoding="utf-8")
            candidate.write_text(golden.read_text(encoding="utf-8"), encoding="utf-8")

            result = verify(
                golden,
                candidate,
                VerificationConfig(mode="unsupported", run_dir=tmp / "run"),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "invalid_input")

    def test_simulation_requires_explicit_observed_outputs(self):
        with workspace_tempdir() as tmp:
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            testbench = tmp / "tb.v"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            testbench.write_text("module tb; initial $finish; endmodule\n", encoding="utf-8")

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    mode="simulation",
                    run_dir=tmp / "run",
                    testbench=testbench,
                ),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "invalid_input")

    def test_sequential_mode_requires_explicit_clock(self):
        with workspace_tempdir() as tmp:
            source = "module top(input clk, input a, output reg y); always @(posedge clk) y <= a; endmodule\n"
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")

            result = verify(
                golden,
                candidate,
                VerificationConfig(sequential=True, run_dir=tmp / "run"),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "invalid_input")

    def test_mock_flag_is_propagated_for_controlled_fake_tool(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            fake_yosys = tmp / "fake_yosys.py"
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            fake_yosys.write_text(
                "import sys\n"
                "assert '-s' in sys.argv\n"
                "print('SAT proof finished - no model found: SUCCESS!')\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    run_dir=tmp / "run",
                    yosys_bin=[sys.executable, str(fake_yosys)],
                    is_mock=True,
                ),
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertTrue(result["is_mock"])
            self.assertEqual(result["proof_level"], "formal")
            self.assertTrue((tmp / "run" / "equivalence.ys").exists())
            self.assertTrue((tmp / "run" / "verify_result.json").exists())

    def test_verify_accepts_plain_dict_config_with_manifest_keys(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            fake_yosys = tmp / "fake_yosys.py"
            source = "module TopModule(input a, output y); assign y = a; endmodule\n"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            fake_yosys.write_text(
                "import sys\n"
                "print('Equivalence successfully proven!')\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                config={
                    "case_id": "case_demo",
                    "top_module": "TopModule",
                    "recommended_induction_steps": 6,
                    "notes": "ignored extra metadata",
                    "run_dir": str(tmp / "run_dict"),
                    "yosys_bin": [sys.executable, str(fake_yosys)],
                    "is_mock": True,
                },
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertTrue((tmp / "run_dict" / "run_metadata.json").exists())

    def test_verify_rejects_non_mapping_config_type_gracefully(self):
        import shutil

        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")

            result = verify(golden, candidate, config="bad_config")  # type: ignore[arg-type]
            try:
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["equivalent"])
                self.assertEqual(result["error_type"], "invalid_input")
            finally:
                if result.get("log_path"):
                    shutil.rmtree(Path(result["log_path"]).parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
