"""Structured verification results and stable status/error vocabulary."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, Optional


VALID_STATUSES = ("success", "failed", "error", "timeout")


@dataclass
class VerificationResult:
    """Result returned by :func:`src.verification.api.verify`.

    ``equivalent`` is deliberately optional.  A tool failure or timeout does
    not provide evidence that the candidate is functionally different.
    ``verification_method`` and ``proof_level`` are additive metadata fields;
    the required interface fields remain unchanged.
    """

    status: str
    equivalent: Optional[bool]
    error_type: Optional[str]
    error_log: Optional[str]
    log_path: Optional[str]
    verification_method: Optional[str] = None
    proof_level: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError("invalid verification status: %s" % self.status)
        if self.status == "success" and self.equivalent is not True:
            raise ValueError("success results must set equivalent=True")
        if self.status == "failed" and self.equivalent is not False:
            raise ValueError("failed results must set equivalent=False")
        if self.status in ("error", "timeout") and self.equivalent is not None:
            raise ValueError("error and timeout results must set equivalent=None")

    @classmethod
    def error(
        cls,
        *,
        error_type: str,
        error_log: Optional[str],
        log_path: Optional[str],
        status: str = "error",
        verification_method: Optional[str] = None,
        proof_level: Optional[str] = None,
    ) -> "VerificationResult":
        return cls(
            status=status,
            equivalent=None,
            error_type=error_type,
            error_log=error_log,
            log_path=log_path,
            verification_method=verification_method,
            proof_level=proof_level,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
