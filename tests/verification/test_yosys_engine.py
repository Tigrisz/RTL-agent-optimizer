import unittest

from src.verification.yosys_engine import (
    build_combinational_miter_script,
    build_equivalence_script,
    build_sequential_bmc_script,
    classify_yosys_result,
    summarize_yosys_error,
)


class YosysEngineTests(unittest.TestCase):
    def test_combinational_scripts_use_double_quotes_structural_and_miter_sat(self):
        script = build_equivalence_script(
            golden="C:\\fixtures\\golden.v",
            candidate="C:\\fixtures\\candidate.v",
            top="TopModule",
        )

        self.assertIn('"C:/fixtures/golden.v"', script)
        self.assertIn('"C:/fixtures/candidate.v"', script)
        self.assertNotIn("'C:/fixtures/golden.v'", script)
        self.assertIn("equiv_make gold gate equiv", script)
        self.assertIn("equiv_struct -icells", script)
        self.assertIn("equiv_simple -undef", script)
        self.assertIn("equiv_status -assert", script)

        miter_script = build_combinational_miter_script(
            golden="C:\\fixtures\\golden.v",
            candidate="C:\\fixtures\\candidate.v",
            top="TopModule",
        )
        self.assertIn("miter -equiv -flatten -make_outputs gold gate miter", miter_script)
        self.assertIn("sat -verify -prove trigger 0", miter_script)

    def test_sequential_script_runs_async2sync_and_induction(self):
        script = build_equivalence_script(
            golden="/fixtures/seq_gold.v",
            candidate="/fixtures/seq_gate.v",
            top="TopModule",
            sequential=True,
            induction_steps=6,
        )

        self.assertIn("async2sync", script)
        self.assertIn("equiv_make gold gate equiv", script)
        self.assertIn("equiv_simple -undef -seq 6", script)
        self.assertIn("equiv_induct -undef -seq 6", script)
        self.assertIn("equiv_status -assert", script)

    def test_sequential_bmc_script_applies_reset_polarity(self):
        script = build_sequential_bmc_script(
            golden="/fixtures/seq_gold.v",
            candidate="/fixtures/seq_gate.v",
            top="TopModule",
            steps=8,
            reset="rst_n",
            reset_active_low=True,
        )

        self.assertIn("async2sync", script)
        self.assertIn("-seq 8", script)
        self.assertIn("-set-at 1 in_rst_n 0 -set-at 2 in_rst_n 1", script)

    def test_real_yosys_052_equiv_status_pass_with_zero_unproven_is_success(self):
        real_log = (
            "13. Executing EQUIV_SIMPLE pass.\n"
            "Proved 40 previously unproven $equiv cells.\n"
            "14. Executing EQUIV_STATUS pass.\n"
            "Found 40 $equiv cells in equiv:\n"
            "  Of those cells 40 are proven and 0 are unproven.\n"
            "  Equivalence successfully proven!\n"
        )
        self.assertEqual(classify_yosys_result(0, real_log), ("success", True, None))

    def test_real_yosys_052_sat_pass_and_fail(self):
        sat_pass = "Solving problem...\nSAT proof finished - no model found: SUCCESS!\n"
        sat_fail = (
            "Solving problem...\n"
            "SAT proof finished - model found: FAIL!\n"
            "  \\gate_out 4 4 00000100\n"
            "  \\gold_out 36 24 00100100\n"
            "ERROR: Called with -verify and proof did fail!\n"
        )
        self.assertEqual(classify_yosys_result(0, sat_pass), ("success", True, None))
        self.assertEqual(classify_yosys_result(1, sat_fail), ("failed", False, "not_equivalent"))

    def test_unproven_and_error_classifications_keep_null_equivalence(self):
        self.assertEqual(
            classify_yosys_result(1, "ERROR: Found 8 unproven $equiv cells in 'equiv_status -assert'."),
            ("error", None, "unproven"),
        )
        self.assertEqual(
            classify_yosys_result(1, "ERROR: No matching port in gate module was found for \\out!"),
            ("error", None, "interface_mismatch"),
        )
        self.assertEqual(
            classify_yosys_result(1, "ERROR: syntax error, unexpected TOK_ENDMODULE"),
            ("error", None, "syntax_error"),
        )
        self.assertEqual(
            classify_yosys_result(1, "ERROR: Module `TopModule' not found!"),
            ("error", None, "missing_top"),
        )
        self.assertEqual(
            classify_yosys_result(1, "ERROR: No SAT model available for async FF cell ($adff)."),
            ("error", None, "unsupported"),
        )
        self.assertEqual(classify_yosys_result(0, ""), ("error", None, "missing_proof"))

    def test_summarize_yosys_error_extracts_counterexample_compactly(self):
        log = (
            "Solving problem...\n"
            "SAT proof finished - model found: FAIL!\n"
            "  Signal Name Dec Hex Bin\n"
            "  \\gate_out 4 4 00000100\n"
            "  \\gold_out 36 24 00100100\n"
            "  \\in_a 20 14 00010100\n"
            "  \\trigger 1 1 1\n"
            "ERROR: Called with -verify and proof did fail!\n"
        )
        summary = summarize_yosys_error(log, "not_equivalent")
        self.assertIn("counterexample found:", summary)
        self.assertIn("gold_out=36(0x24)", summary)
        self.assertIn("gate_out=4(0x4)", summary)
        self.assertNotIn("trigger=", summary)


if __name__ == "__main__":
    unittest.main()
