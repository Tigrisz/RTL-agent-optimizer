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
    @unittest.skipUnless(OPTI_DEMO_ROOT.is_dir(), "local opti_demo cases are not present")
    def test_opti_demo_addsubz_both_mode_and_cli(self):
        with workspace_tempdir() as tmp:
            gold = OPTI_DEMO_ROOT / "case/bench/addsubz/addsubz_v1_behavioral.v"
            cand = OPTI_DEMO_ROOT / "case/bench/addsubz/addsubz_v2_ripple.v"
            stim = OPTI_DEMO_ROOT / "case/bench/tb/stim_addsubz.v"

            result = verify(
                gold,
                cand,
                VerificationConfig(
                    top="TopModule",
                    mode="both",
                    testbench=stim,
                    observed_outputs=("out", "result_is_zero"),
                    run_dir=tmp / "run_both",
                ),
            )
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["equivalent"])
            self.assertEqual(result["proof_level"], "formal+bounded-simulation")

            # Also smoke-test the CLI entry point.
            repo_root = Path(__file__).resolve().parents[2]
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.verification",
                    str(gold),
                    str(cand),
                    "--top",
                    "TopModule",
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

    @unittest.skipUnless(OPTI_DEMO_ROOT.is_dir(), "local opti_demo cases are not present")
    def test_opti_demo_opt_top_and_mac8_simulation(self):
        with workspace_tempdir() as tmp:
            # opt_top formal + simulation (optimized shared-multiplier candidate)
            gold_opt = OPTI_DEMO_ROOT / "case/rtl/opt_top.v"
            stim_opt = OPTI_DEMO_ROOT / "case/rtl/stim_opt_top.v"
            shared_opt = tmp / "opt_top_shared.v"
            shared_opt.write_text(
                "module opt_top #(parameter W = 8) (\n"
                "  input wire [W-1:0] a, input wire [W-1:0] b,\n"
                "  input wire [W-1:0] c, input wire [W-1:0] d,\n"
                "  input wire sel, output wire [2*W-1:0] y\n"
                ");\n"
                "  wire [W-1:0] lhs = sel ? c : a;\n"
                "  wire [W-1:0] rhs = sel ? d : b;\n"
                "  assign y = lhs * rhs;\n"
                "endmodule\n",
                encoding="utf-8",
            )

            res_opt = verify(
                gold_opt,
                shared_opt,
                VerificationConfig(
                    top="opt_top",
                    mode="both",
                    testbench=stim_opt,
                    observed_outputs=("y",),
                    run_dir=tmp / "run_opt",
                ),
            )
            self.assertEqual(res_opt["status"], "success")
            self.assertTrue(res_opt["equivalent"])
            self.assertEqual(res_opt["proof_level"], "formal+bounded-simulation")

            # mac8 sequential formal + simulation
            gold_mac = OPTI_DEMO_ROOT / "case/bench/mac8/mac8_v4_seq_shared.v"
            stim_mac = OPTI_DEMO_ROOT / "case/bench/tb/stim_mac8.v"
            res_mac = verify(
                gold_mac,
                gold_mac,
                VerificationConfig(
                    top="TopModule",
                    mode="both",
                    sequential=True,
                    clock="clk",
                    reset="rst",
                    induction_steps=4,
                    testbench=stim_mac,
                    observed_outputs=("done", "y"),
                    run_dir=tmp / "run_mac",
                ),
            )
            self.assertEqual(res_mac["status"], "success")
            self.assertTrue(res_mac["equivalent"])
            self.assertEqual(res_mac["proof_level"], "bounded-formal+bounded-simulation")

            # Simulation mismatch catches a real bug and reports timestamp
            buggy_opt = tmp / "opt_top_buggy.v"
            buggy_opt.write_text(
                "module opt_top #(parameter W = 8) (\n"
                "  input wire [W-1:0] a, input wire [W-1:0] b,\n"
                "  input wire [W-1:0] c, input wire [W-1:0] d,\n"
                "  input wire sel, output wire [2*W-1:0] y\n"
                ");\n"
                "  assign y = a * b;\n"
                "endmodule\n",
                encoding="utf-8",
            )
            res_sim_fail = verify(
                gold_opt,
                buggy_opt,
                VerificationConfig(
                    top="opt_top",
                    mode="simulation",
                    testbench=stim_opt,
                    observed_outputs=("y",),
                    run_dir=tmp / "run_opt_bug",
                ),
            )
            self.assertEqual(res_sim_fail["status"], "failed")
            self.assertFalse(res_sim_fail["equivalent"])
            self.assertEqual(res_sim_fail["error_type"], "not_equivalent")
            self.assertIn("waveform mismatch on", res_sim_fail["error_log"])
            self.assertIn("at t=", res_sim_fail["error_log"])


if __name__ == "__main__":
    unittest.main()
