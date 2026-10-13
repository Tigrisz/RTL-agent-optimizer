# Task B：Verification

`src/verification` 提供候选 RTL 的独立验证入口。它不修改 golden RTL，也不把候选文件覆盖到基准目录；每次运行都会在独立目录中保存脚本、完整工具日志、运行元数据和 JSON 结果，便于任务 A 或后续联调复现。

## 调用方式

```python
from src.verification import VerificationConfig, verify

result = verify(
    golden_rtl="bench/golden.v",
    candidate_rtl="runs/candidate.v",
    config=VerificationConfig(
        top="top",
        mode="formal",
        timeout_seconds=120,
    ),
)
```

`VerificationConfig` 支持多文件设计（`extra_sources`）、头文件目录（`include_dirs`）、宏定义（`defines`）以及工具路径。工具路径按“配置对象 > 进程环境变量 > `tools.env` > PATH”解析；环境变量名称分别是 `YOSYS_BIN`、`IVERILOG_BIN` 和 `VVP_BIN`。

## 验证模式

- `formal`：使用 Yosys 读取 golden 和 candidate，构造 `$equiv` 电路并运行 `equiv_simple`；组合逻辑成功结果的 `proof_level` 为 `formal`。
- `simulation`：使用 Icarus Verilog/VVP 对同一个 testbench 分别运行 golden 和 candidate，并比较指定观测信号的完整 VCD 波形。必须显式提供 `testbench` 和 `observed_outputs`，否则不能判断回归结果。
- `both`：先通过 Yosys，再通过 bounded simulation；两者都成功才返回成功。

顺序逻辑需要显式设置 `sequential=True` 和 `clock`。当前后端使用有限步数的 `equiv_simple/equiv_induct` 检查，因此成功结果标记为 `bounded-formal`，不把有限步归纳结果误报成无界证明。`reset`、`reset_active_low` 会写入运行元数据，具体复位假设应由后续时序约束和 testbench 明确表达。

## 结果契约

`verify` 返回 JSON-compatible 字典，至少包含：

| 字段 | 含义 |
| --- | --- |
| `status` | `success`、`failed`、`error` 或 `timeout` |
| `equivalent` | 成功为 `true`，确认不等价为 `false`，工具错误/超时为 `null` |
| `error_type` | 例如 `not_equivalent`、`tool_error`、`timeout`、`missing_observation` |
| `error_log` | 面向调用者的诊断摘要 |
| `log_path` | 完整日志路径 |

`success` 只在后端明确报告证明完成或回归波形一致时产生；Yosys 返回空成功码、unproven、unknown 或 unsupported 都会分类为 `error`，避免把工具异常当成等价。

## 与其他任务联调

任务 A 只需把候选 RTL 路径传给 `verify` 并读取返回字典。建议将 `run_dir` 绑定到该轮优化的唯一目录，保留 `run_metadata.json`、`equivalence.ys`、`yosys.log`、回归编译/运行日志及 `verify_result.json`。任务 C/D 可以直接读取 `status`、`equivalent`、`proof_level` 和 `error_type`，不需要解析 Yosys 文本。

当前仓库没有随源码提供公开 benchmark RTL，且本机 Windows PATH/WSL 环境尚未能启动 Yosys 和 Icarus；因此单元测试使用可控的假工具覆盖接口、脚本生成、超时、分类和 VCD 比较。接入真实工具后，应再用 Demo 之外的组合和时序样例执行一次端到端回归，并把真实日志留在对应 run 目录中。
