"""End-to-end verification tests running against real Yosys and Icarus Verilog."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from src.verification import VerificationConfig, verify
from test_support import workspace_tempdir


HAS_YOSYS = shutil.which("yosys") is not None
HAS_SIM = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
OPTI_DEMO_ROOT = Path(__file__).resolve().parents[3] / "opti_demo"


@unittest.skipUnless(HAS_YOSYS, "real yosys binary is required")
class RealYosysFormalTests(unittest.TestCase):
    def test_combinational_structurally_different_designs_prove_equivalent(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "gold.v"
            candidate = tmp / "gate.v"
            golden.write_text(
                "module TopModule(input do_sub, input [7:0] a, input [7:0] b, "
                "output reg [7:0] out, output reg result_is_zero);\n"
                "  always @(*) begin\n"
                "    out = do_sub ? a - b : a + b;\n"
                "    result_is_zero = (out == 8'b0);\n"
                "  end\n"
                "endmodule\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "module TopModule(input do_sub, input [7:0] a, input [7:0] b, "
                "output reg [7:0] out, output reg result_is_zero);\n"
                "  wire [7:0] bb = b ^ {8{do_sub}};\n"
                "  wire [8:0] sum = a + bb + do_sub;\n"
                "  always @(*) begin\n"
                "    out = sum[7:0];\n"
                "    result_is_zero = (out == 8'b0);\n"
                "  end\n"
                "endmodule\n",
                encoding="utf-8",
            )

            result = verify(golden, candidate, VerificationConfig(top="TopModule", run_dir=tmp / "run"))

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertIsNone(result["error_type"])
            self.assertEqual(result["proof_level"], "formal")
            self.assertFalse(result["is_mock"])

    def test_combinational_bug_reports_not_equivalent_with_counterexample(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "gold.v"
            candidate = tmp / "gate.v"
            golden.write_text(
                "module TopModule(input do_sub, input [7:0] a, input [7:0] b, output [7:0] out);\n"
                "  assign out = do_sub ? (a - b) : (a + b);\n"
                "endmodule\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "module TopModule(input do_sub, input [7:0] a, input [7:0] b, output [7:0] out);\n"
                "  assign out = a + b;\n"
                "endmodule\n",
                encoding="utf-8",
            )

            result = verify(golden, candidate, VerificationConfig(top="TopModule", run_dir=tmp / "run"))

            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["equivalent"])
            self.assertEqual(result["error_type"], "not_equivalent")
            self.assertIn("counterexample found:", result["error_log"])
            self.assertIn("gold_out=", result["error_log"])
            self.assertIn("gate_out=", result["error_log"])

    def test_port_mismatch_and_syntax_error_return_error_with_null_equivalence(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "gold.v"
            bad_port = tmp / "bad_port.v"
            bad_syntax = tmp / "bad_syntax.v"
            golden.write_text(
                "module TopModule(input [3:0] a, output [3:0] y); assign y = a; endmodule\n",
                encoding="utf-8",
            )
            bad_port.write_text(
                "module TopModule(input [3:0] a, output [3:0] z); assign z = a; endmodule\n",
                encoding="utf-8",
            )
            bad_syntax.write_text(
                "module TopModule(input [3:0] a, output [3:0] y); assign y = ; endmodule\n",
                encoding="utf-8",
            )

            res_port = verify(golden, bad_port, VerificationConfig(top="TopModule", run_dir=tmp / "r_port"))
            self.assertEqual(res_port["status"], "error")
            self.assertIsNone(res_port["equivalent"])
            self.assertEqual(res_port["error_type"], "interface_mismatch")

            res_syn = verify(golden, bad_syntax, VerificationConfig(top="TopModule", run_dir=tmp / "r_syn"))
            self.assertEqual(res_syn["status"], "error")
            self.assertIsNone(res_syn["equivalent"])
            self.assertEqual(res_syn["error_type"], "syntax_error")

    def test_sequential_async_reset_equiv_and_bug_detection(self):
        with workspace_tempdir() as tmp:
            golden = tmp / "seq_gold.v"
            equiv_gate = tmp / "seq_equiv.v"
            buggy_gate = tmp / "seq_buggy.v"
            golden.write_text(
                "module seq_acc(input clk, input rst, input en, input [7:0] d, output reg [7:0] q);\n"
                "  always @(posedge clk or posedge rst) begin\n"
                "    if (rst) q <= 8'd0;\n"
                "    else if (en) q <= q + d;\n"
                "  end\n"
                "endmodule\n",
                encoding="utf-8",
            )
            equiv_gate.write_text(
                "module seq_acc(input clk, input rst, input en, input [7:0] d, output reg [7:0] q);\n"
                "  wire [7:0] next_q = en ? (q + d) : q;\n"
                "  always @(posedge clk or posedge rst) begin\n"
                "    if (rst) q <= 8'd0;\n"
                "    else q <= next_q;\n"
                "  end\n"
                "endmodule\n",
                encoding="utf-8",
            )
            buggy_gate.write_text(
                "module seq_acc(input clk, input rst, input en, input [7:0] d, output reg [7:0] q);\n"
                "  always @(posedge clk or posedge rst) begin\n"
                "    if (rst) q <= 8'd0;\n"
                "    else if (en) q <= q - d;\n"
                "  end\n"
                "endmodule\n",
                encoding="utf-8",
            )

            res_ok = verify(
                golden,
                equiv_gate,
                VerificationConfig(
                    top="seq_acc",
                    sequential=True,
                    clock="clk",
                    reset="rst",
                    induction_steps=4,
                    run_dir=tmp / "r_seq_ok",
                ),
            )
            self.assertEqual(res_ok["status"], "success")
            self.assertTrue(res_ok["equivalent"])
            self.assertEqual(res_ok["proof_level"], "bounded-formal")

            res_bug = verify(
                golden,
                buggy_gate,
                VerificationConfig(
                    top="seq_acc",
                    sequential=True,
                    clock="clk",
                    reset="rst",
                    induction_steps=4,
                    run_dir=tmp / "r_seq_bug",
                ),
            )
            self.assertEqual(res_bug["status"], "failed")
            self.assertFalse(res_bug["equivalent"])
            self.assertEqual(res_bug["error_type"], "not_equivalent")
            self.assertIn("counterexample found:", res_bug["error_log"])


@unittest.skipUnless(HAS_YOSYS and HAS_SIM, "real yosys, iverilog, and vvp are required")
class RealOptiDemoCasesTests(unittest.TestCase):
    PUBLIC_CASES = (
        ("case1", "barrel_shifter", False, None, None, False, ("out",)),
        ("case2", "fp_rounding", False, None, None, False, ("abs_rounded_o", "sign_o", "exact_zero_o")),
        ("case3", "fixed_point_subtractor", False, None, None, False, ("c",)),
        ("case4", "div_16bit", False, None, None, False, ("result", "odd")),
        ("case5", "verified_accu", True, "clk", "rst_n", True, ("valid_out", "data_out")),
        ("case6", "LIFObuffer", True, "clk", "Rst", False, ("EMPTY", "FULL", "dataOut")),
        ("case7", "verified_adder_64bit", True, "clk", "rst_n", True, ("result", "o_en")),
        ("case8", "verified_radix2_div", True, "clk", "rst", False, ("res_valid", "result")),
    )

    @unittest.skipUnless((OPTI_DEMO_ROOT / "case" / "case1" / "rtl.v").is_file(), "official 8 TA cases are not present")
    def test_all_eight_official_ta_public_cases_pass_both_mode(self):
        with workspace_tempdir() as tmp:
            for cid, top, seq, clk, rst, rst_low, obs in self.PUBLIC_CASES:
                rtl = OPTI_DEMO_ROOT / "case" / cid / "rtl.v"
                tb = OPTI_DEMO_ROOT / "case" / "tb" / (cid + "_tb.v")
                result = verify(
                    rtl,
                    rtl,
                    VerificationConfig(
                        top=top,
                        mode="both",
                        timeout_seconds=30,
                        sequential=seq,
                        clock=clk,
                        reset=rst,
                        reset_active_low=rst_low,
                        testbench=tb,
                        observed_outputs=obs,
                        run_dir=tmp / cid,
                    ),
                )
                expected_proof = (
                    "bounded-formal+bounded-simulation" if seq else "formal+bounded-simulation"
                )
                self.assertEqual(result["status"], "success", "%s failed: %s" % (cid, result))
                self.assertTrue(result["equivalent"], cid)
                self.assertEqual(result["proof_level"], expected_proof, cid)

    @unittest.skipUnless((OPTI_DEMO_ROOT / "case" / "case1" / "rtl.v").is_file(), "official 8 TA cases are not present")
    def test_case1_optimized_rewrite_bug_detection_and_cli(self):
        with workspace_tempdir() as tmp:
            gold = OPTI_DEMO_ROOT / "case" / "case1" / "rtl.v"
            tb = OPTI_DEMO_ROOT / "case" / "tb" / "case1_tb.v"

            # Structurally different behavioral rewrite of barrel_shifter
            rewritten = tmp / "barrel_shifter_opt.v"
            rewritten.write_text(
                "module barrel_shifter(input [7:0] in, input [2:0] ctrl, output [7:0] out);\n"
                "  assign out = in >> ctrl;\n"
                "endmodule\n",
                encoding="utf-8",
            )
            res_opt = verify(
                gold,
                rewritten,
                VerificationConfig(
                    top="barrel_shifter",
                    mode="both",
                    testbench=tb,
                    observed_outputs=("out",),
                    run_dir=tmp / "run_opt",
                ),
            )
            self.assertEqual(res_opt["status"], "success", res_opt)
            self.assertTrue(res_opt["equivalent"])
            self.assertEqual(res_opt["proof_level"], "formal+bounded-simulation")

            # Buggy candidate caught in simulation with timestamp
            buggy = tmp / "barrel_shifter_buggy.v"
            buggy.write_text(
                "module barrel_shifter(input [7:0] in, input [2:0] ctrl, output [7:0] out);\n"
                "  assign out = in << ctrl;\n"
                "endmodule\n",
                encoding="utf-8",
            )
            res_sim_fail = verify(
                gold,
                buggy,
                VerificationConfig(
                    top="barrel_shifter",
                    mode="simulation",
                    testbench=tb,
                    observed_outputs=("out",),
                    run_dir=tmp / "run_bug",
                ),
            )
            self.assertEqual(res_sim_fail["status"], "failed")
            self.assertFalse(res_sim_fail["equivalent"])
            self.assertEqual(res_sim_fail["error_type"], "not_equivalent")
            self.assertIn("waveform mismatch on", res_sim_fail["error_log"])
            self.assertIn("at t=", res_sim_fail["error_log"])

            # CLI smoke test on real case1
            repo_root = Path(__file__).resolve().parents[2]
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.verification",
                    str(gold),
                    str(rewritten),
                    "--top",
                    "barrel_shifter",
                    "--mode",
                    "formal",
                    "--run-dir",
                    str(tmp / "run_cli"),
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "success")
            self.assertTrue(payload["equivalent"])


if __name__ == "__main__":
    unittest.main()
