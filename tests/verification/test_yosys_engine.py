import unittest

from src.verification.yosys_engine import build_equivalence_script, classify_yosys_result


class YosysEngineTests(unittest.TestCase):
    def test_script_contains_equivalence_pipeline(self):
        script = build_equivalence_script(
            golden=":/fixtures/golden.v",
            candidate=":/fixtures/candidate.v",
            top="top",
        )

        self.assertIn("equiv_make", script)
        self.assertIn("equiv_simple", script)
        self.assertIn("equiv_status -assert", script)
        self.assertIn("golden.v", script)
        self.assertIn("candidate.v", script)

    def test_success_and_counterexample_are_distinct(self):
        passed = classify_yosys_result(0, "Equivalence successfully proven")
        failed = classify_yosys_result(1, "ERROR: counterexample found; outputs mismatch")

        self.assertEqual(passed, ("success", True, None))
        self.assertEqual(failed, ("failed", False, "not_equivalent"))

    def test_unproven_or_unsupported_is_unknown_equivalence(self):
        result = classify_yosys_result(1, "ERROR: Found unproven $equiv cells")

        self.assertEqual(result[0], "error")
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "unproven")

    def test_tool_failure_is_unknown_equivalence(self):
        result = classify_yosys_result(1, "syntax error in source")

        self.assertEqual(result[0], "error")
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "tool_error")

    def test_empty_success_output_is_not_proof(self):
        result = classify_yosys_result(0, "")

        self.assertEqual(result, ("error", None, "missing_proof"))


if __name__ == "__main__":
    unittest.main()
