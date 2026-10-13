import json
import unittest

from src.verification.result import VerificationResult


class VerificationResultTests(unittest.TestCase):
    def test_result_serializes_required_fields_and_optional_method(self):
        result = VerificationResult(
            status="success",
            equivalent=True,
            error_type=None,
            error_log=None,
            log_path="C:/runs/case1/verify.log",
            verification_method="yosys-formal",
            proof_level="formal",
        )

        payload = result.to_dict()

        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["equivalent"])
        self.assertEqual(payload["log_path"], "C:/runs/case1/verify.log")
        self.assertEqual(payload["verification_method"], "yosys-formal")
        self.assertEqual(payload["proof_level"], "formal")
        json.dumps(payload)

    def test_error_result_uses_null_equivalence(self):
        result = VerificationResult.error(
            error_type="timeout",
            error_log="tool exceeded timeout",
            log_path="/tmp/verify.log",
            status="timeout",
        )

        self.assertEqual(result.status, "timeout")
        self.assertIsNone(result.equivalent)
        self.assertEqual(result.error_type, "timeout")


if __name__ == "__main__":
    unittest.main()
