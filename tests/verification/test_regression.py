import unittest

from src.verification.regression import _compare_vcd, _normalize_vcd_vector, _parse_vcd, _render_testbench
from test_support import workspace_tempdir


class RegressionUnitTests(unittest.TestCase):
    def test_render_testbench_replaces_vcd_and_seed(self):
        with workspace_tempdir() as tmp:
            tb = tmp / "stim.v"
            tb.write_text('$dumpfile("__VCD__"); rnd = __SEED__;\n', encoding="utf-8")
            rendered = _render_testbench(tb, tmp / "out.vcd", seed=12345)
            self.assertIn("out.vcd", rendered)
            self.assertIn("rnd = 12345;", rendered)
            self.assertNotIn("__VCD__", rendered)
            self.assertNotIn("__SEED__", rendered)

    def test_normalize_vcd_vector_preserves_unknown_vs_zero_prefix(self):
        self.assertEqual(_normalize_vcd_vector("1", 4), "0001")
        self.assertEqual(_normalize_vcd_vector("x", 4), "xxxx")
        self.assertEqual(_normalize_vcd_vector("000x", 4), "000x")
        self.assertNotEqual(_normalize_vcd_vector("000x", 4), _normalize_vcd_vector("x", 4))

    def test_parse_vcd_keeps_aliased_signals_and_reports_first_mismatch_time(self):
        with workspace_tempdir() as tmp:
            vcd_a = tmp / "a.vcd"
            vcd_b = tmp / "b.vcd"
            header = (
                "$scope module tb $end\n"
                "$var wire 4 ! top_y [3:0] $end\n"
                "$scope module dut $end\n"
                "$var wire 4 ! y [3:0] $end\n"
                "$upscope $end\n"
                "$upscope $end\n"
                "$enddefinitions $end\n"
            )
            vcd_a.write_text(header + "#0\nb0001 !\n#10\nb0101 !\n", encoding="utf-8")
            vcd_b.write_text(header + "#0\nb1 !\n#10\nb0111 !\n", encoding="utf-8")

            parsed = _parse_vcd(vcd_a)
            self.assertIn("tb.top_y", parsed)
            self.assertIn("tb.dut.y", parsed)

            status, detail = _compare_vcd(vcd_a, vcd_b, ("dut.y",))
            self.assertEqual(status, "failed")
            self.assertIn("at t=10", detail)
            self.assertIn("golden=0101", detail)
            self.assertIn("candidate=0111", detail)

    def test_compare_vcd_ignores_zero_delay_delta_glitches(self):
        with workspace_tempdir() as tmp:
            vcd_a = tmp / "a.vcd"
            vcd_b = tmp / "b.vcd"
            header = (
                "$scope module tb $end\n"
                "$var wire 1 ! z $end\n"
                "$upscope $end\n"
                "$enddefinitions $end\n"
            )
            vcd_a.write_text(header + "#0\n0!\n#20\n1!\n", encoding="utf-8")
            # Same settled waveform, but with a delta glitch at t=0 and no-op update at t=10.
            vcd_b.write_text(header + "#0\nx!\n0!\n#10\n0!\n#20\n1!\n", encoding="utf-8")

            status, detail = _compare_vcd(vcd_a, vcd_b, ("z",))
            self.assertEqual(status, "success", detail)


if __name__ == "__main__":
    unittest.main()
