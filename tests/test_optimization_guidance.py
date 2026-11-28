import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.optimization import optimize
from src.optimization.feedback import performance_summary
from src.optimization.optimizer import extract_candidate, select_strategy
from src.optimization.structures import opportunities


class GuidanceTests(unittest.TestCase):
    def test_plan_depends_on_dataflow(self):
        pipeline = """
        always @(posedge clk) begin
            u1 <= x; u2 <= u1; v1 <= y; v2 <= v1;
            if (valid) result <= u2 + v2 + cin;
        end
        """
        plans = opportunities(pipeline)
        self.assertEqual(plans["pipeline_partial_sum"]["copy_stages"], 2)
        self.assertEqual(select_strategy({}, plans), "pipeline_partial_sum")
        self.assertEqual(select_strategy({"tried_strategies": ["pipeline_partial_sum"]}, plans),
                         "pipeline_block_carry")
        arithmetic = "assign out = sel ? a[W-1:0] + b : b - a[W-1:0];"
        self.assertEqual(select_strategy({}, opportunities(arithmetic)), "shared_add_sub")
        self.assertFalse(opportunities("// " + arithmetic))
        self.assertFalse(opportunities("assign v = sel ? a+b : c-d;"))

    def test_depth_regression_without_timing_limit(self):
        feedback = {"baseline": {"area": 100, "delay": 33},
                    "evaluate": {"status": "success", "area": 80, "delay": 40, "timing_met": None}}
        summary = performance_summary(feedback, {})
        self.assertEqual(summary["metrics"]["logic_depth"]["delta"], 7)
        self.assertEqual(summary["metrics"]["area"]["delta"], -20)
        self.assertIsNone(summary["timing_met"])
        self.assertEqual(select_strategy(feedback, performance=summary), "timing_restructure")

    def test_failed_sta_and_incomparable_measurements(self):
        feedback = {"baseline": {"area": 80, "config_version": "a", "delay": 100, "delay_unit": "ps"},
                    "evaluate": {"status": "success", "config_version": "b", "area": 70, "delay": 1,
                                 "delay_unit": "ns", "sta": {"status": "error", "slack": -1, "unit": "ns"}}}
        metrics = performance_summary(feedback, {})["metrics"]
        self.assertNotIn("logic_depth", metrics)
        self.assertNotIn("slack", metrics)
        self.assertIsNone(metrics["path_delay"]["delta"])
        self.assertIsNone(metrics["area"]["delta"])
        feedback["evaluate"]["status"] = "timeout"
        self.assertIsNone(performance_summary(feedback, {})["metrics"]["area"]["candidate"])

    def test_sta_violation_overrides_depth_improvement(self):
        feedback = {"baseline": {"delay": 33}, "evaluate": {"status": "success", "delay": 28,
                    "sta": {"status": "success", "path_delay": 2.3, "slack": -0.3, "unit": "ns",
                            "startpoint": "r1/Q", "endpoint": "r2/D"}}}
        summary = performance_summary(feedback, {})
        self.assertEqual(summary["critical_path"]["endpoint"], "r2/D")
        self.assertEqual(summary["metrics"]["path_delay"]["unit"], "ns")
        self.assertEqual(select_strategy(feedback, {"pipeline_block_carry": {}}, summary),
                         "pipeline_block_carry")
        feedback["verify"] = {"status": "error", "error_type": "syntax_error"}
        self.assertEqual(select_strategy(feedback, performance=summary), "repair_interface")

    def test_legacy_depth_cannot_check_nanosecond_limit(self):
        feedback = {"evaluate": {"status": "success", "delay": 10, "timing_met": False}}
        summary = performance_summary(feedback, {"constraints": {"delay_limit": 3, "delay_unit": "ns"}})
        self.assertEqual(summary["timing_metric"], "logic_depth")
        self.assertIsNone(summary["timing_met"])
        self.assertEqual(select_strategy(feedback, performance=summary), "area_simplify")

    def test_unique_anchor_reconstruction(self):
        source = "module m; wire a; wire b; endmodule\n"
        def edit(old, new):
            return "```json\n" + json.dumps(dict(old=old, new=new)) + "\n```"
        changed = extract_candidate(edit("wire a;", "logic a;"), source, ".sv")
        self.assertEqual(changed, (source.replace("wire a;", "logic a;"), ".sv"))
        for old, new in [("wire", "reg"), ("missing", "z"), ("endmodule", ""), ("", "text")]:
            self.assertIsNone(extract_candidate(edit(old, new), source, ".v"))

    def test_custom_pipeline_from_edit_to_saved_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.v"
            src.write_text("module m(input a, b, output y); assign y = a & b; endmodule\n")
            env = {"LLM_BASE_URL": "https://example.invalid", "LLM_MODEL": "test", "LLM_API_KEY": "unused"}
            feedback = {"baseline": {"delay": 5}, "evaluate": {"status": "success", "delay": 6}}
            def generate(old, new):
                reply = "```json\n" + json.dumps(dict(old=old, new=new)) + "\n```"
                with patch.dict("os.environ", env, clear=True), patch(
                        "src.optimization.optimizer.call_model", return_value=reply) as model:
                    result = optimize(src, feedback, backend="custom", env_file=None,
                                      output_dir=root, context={"top": "m"})
                self.assertIn('"logic_depth"', model.call_args.args[0])
                return result
            result = generate("a & b", "b & a")
            self.assertEqual(result["status"], "success")
            self.assertIn("b & a", Path(result["candidate_path"]).read_text())
            record = json.loads(Path(result["record_path"]).read_text(encoding="utf-8"))
            self.assertEqual(record["guidance"]["performance"]["metrics"]["logic_depth"]["delta"], 1)
            rejected = generate("output y", "output z")
            self.assertIsNone(rejected["candidate_path"])
            self.assertEqual(rejected["error_type"], "interface_changed")
