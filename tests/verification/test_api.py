import unittest
from pathlib import Path
import sys

from src.verification.api import verify
from src.verification.config import VerificationConfig
from test_support import workspace_tempdir


class VerificationApiValidationTests(unittest.TestCase):
    def test_missing_golden_file_is_an_error_with_null_equivalence(self):
        with workspace_tempdir() as tmp:
            result = verify(
                tmp / "missing.v",
                tmp / "candidate.v",
                VerificationConfig(run_dir=tmp / "run"),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "missing_file")
            self.assertTrue(Path(result["log_path"]).exists())

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

    def test_formal_pass_is_returned_as_success(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            fake_yosys = tmp / "fake_yosys.py"
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            fake_yosys.write_text(
                "import sys\n"
                "script = sys.argv[sys.argv.index('-p') + 1]\n"
                "print('Equivalence successfully proven')\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    run_dir=tmp / "run",
                    yosys_bin=[sys.executable, str(fake_yosys)],
                ),
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertEqual(result["proof_level"], "formal")
            self.assertTrue((tmp / "run" / "equivalence.ys").exists())
            self.assertTrue((tmp / "run" / "verify_result.json").exists())

    def test_formal_counterexample_is_not_equivalent(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            fake_yosys = tmp / "fake_yosys.py"
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            fake_yosys.write_text(
                "import sys\n"
                "print('counterexample found; outputs mismatch')\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    run_dir=tmp / "run",
                    yosys_bin=[sys.executable, str(fake_yosys)],
                ),
            )

            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["equivalent"])
            self.assertEqual(result["error_type"], "not_equivalent")

    def test_simulation_mode_records_bounded_proof(self):
        with workspace_tempdir() as tmp:
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            testbench = tmp / "tb.v"
            fake_iverilog = tmp / "fake_iverilog.py"
            fake_vvp = tmp / "fake_vvp.py"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            testbench.write_text("module tb; initial $finish; endmodule\n", encoding="utf-8")
            fake_iverilog.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('fake')\n",
                encoding="utf-8",
            )
            fake_vvp.write_text(
                "import pathlib, sys\n"
                "name = pathlib.Path(sys.argv[1]).stem\n"
                "vcd = pathlib.Path.cwd() / ('candidate.vcd' if 'candidate' in name else 'golden.vcd')\n"
                "vcd.write_text('$scope module dut $end\\n$var wire 1 ! y $end\\n$upscope $end\\n$enddefinitions $end\\n#0\\n0!\\n#1\\n1!\\n')\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    mode="simulation",
                    run_dir=tmp / "run",
                    testbench=testbench,
                    observed_outputs=("y",),
                    iverilog_bin=[sys.executable, str(fake_iverilog)],
                    vvp_bin=[sys.executable, str(fake_vvp)],
                ),
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertEqual(result["proof_level"], "bounded-simulation")

    def test_simulation_without_observed_values_is_an_error(self):
        with workspace_tempdir() as tmp:
            source = "module top(input a, output y); assign y = a; endmodule\n"
            golden = tmp / "golden.v"
            candidate = tmp / "candidate.v"
            testbench = tmp / "tb.v"
            fake_iverilog = tmp / "fake_iverilog.py"
            fake_vvp = tmp / "fake_vvp.py"
            golden.write_text(source, encoding="utf-8")
            candidate.write_text(source, encoding="utf-8")
            testbench.write_text("module tb; initial $finish; endmodule\n", encoding="utf-8")
            fake_iverilog.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('fake')\n",
                encoding="utf-8",
            )
            fake_vvp.write_text(
                "import pathlib, sys\n"
                "name = pathlib.Path(sys.argv[1]).stem\n"
                "vcd = pathlib.Path.cwd() / ('candidate.vcd' if 'candidate' in name else 'golden.vcd')\n"
                "vcd.write_text('$scope module dut $end\\n$var wire 1 ! y $end\\n$upscope $end\\n$enddefinitions $end\\n')\n",
                encoding="utf-8",
            )

            result = verify(
                golden,
                candidate,
                VerificationConfig(
                    mode="simulation",
                    run_dir=tmp / "run",
                    testbench=testbench,
                    observed_outputs=("y",),
                    iverilog_bin=[sys.executable, str(fake_iverilog)],
                    vvp_bin=[sys.executable, str(fake_vvp)],
                ),
            )

            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["equivalent"])
            self.assertEqual(result["error_type"], "missing_observation")


if __name__ == "__main__":
    unittest.main()
