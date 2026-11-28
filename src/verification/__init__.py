"""B：等价验证、正确性回归与验证失败分类。"""

from .api import verify
from .config import VerificationConfig

__all__ = ["VerificationConfig", "verify"]
