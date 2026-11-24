# Task B：Verification

`src/verification` 提供候选 RTL 的独立验证入口。它不修改 golden RTL，也不把候选文件覆盖到基准目录；每次运行都会在独立目录中保存脚本、完整工具日志、运行元数据和 JSON 结果，便于任务 A 或后续联调复现。

## 调用方式

### Python API

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

### 命令行入口（CLI）

```bash
python -m src.verification golden.v candidate.v --top TopModule --mode formal --run-dir runs/verify_demo
```

`VerificationConfig` 支持多文件设计（`extra_sources`）、头文件目录（`include_dirs`）、宏定义（`defines`）、随机激励种子（`seed`，自动替换 testbench 中的 `__SEED__`）、`is_mock` 标记以及工具路径。工具路径按“配置对象 > 进程环境变量 > `tools.env` > PATH”解析；环境变量名称分别是 `YOSYS_BIN`、`IVERILOG_BIN` 和 `VVP_BIN`。

## 验证模式

- `formal`：
  - **组合电路**（`sequential=False`）：采用两阶段形式验证。第一阶段执行 `equiv_make` + `equiv_struct -icells` + `equiv_simple -undef` + `equiv_status -assert`，可在亚秒级证明 `div_16bit` 等含共享子结构的大型组合电路；若仍有未证明 `$equiv` 单元（例如跨架构重写或存在真实 bug），自动在剩余超时预算内进入第二阶段 `miter -equiv -flatten -make_outputs gold gate miter` + `sat -verify -prove trigger 0 -show-inputs -show-outputs -set-def-inputs miter`，完成形式等价证明（`proof_level="formal"`）或输出具体 SAT 反例信号表。
  - **时序电路**（`sequential=True`，需显式设置 `clock`）：在 `proc; flatten;` 后自动执行 `async2sync` 以兼容异步复位寄存器（`$adff`），再执行 `equiv_struct -icells` + 有限步 `equiv_simple/equiv_induct` 和 `equiv_status -assert`，成功结果标记为 `proof_level="bounded-formal"`。若归纳阶段存在未证明单元（`unproven`），在剩余超时预算内自动追加有界 `miter + sat -seq` 反例搜索（支持根据 `reset`/`reset_active_low` 施加复位约束），命中反例则精确分类为 `not_equivalent`，未命中反例则保持保守的 `error / unproven`，不误报为等价。
- `simulation`：使用 Icarus Verilog/VVP 对同一个 testbench 分别运行 golden 和 candidate，替换 `__VCD__` / `` `VCD_PATH `` / `__SEED__`，按 IEEE 1364 位宽左扩展规则解析 VCD（保留共享 symbol 的别名信号，并折叠同时间戳的零延时 delta 周期毛刺与冗余无变化事件），逐信号比对 `observed_outputs`，不一致时报告首个分歧时间戳及 golden/candidate 信号值。必须显式提供 `testbench` 和 `observed_outputs`。
- `both`：先通过 Yosys 形式验证，再通过 bounded simulation；两者都成功才返回成功（`formal+bounded-simulation` 或 `bounded-formal+bounded-simulation`）。若形式验证阶段返回未收敛（`error / unproven`），仍会继续执行仿真回归：一旦仿真捕获真实波形分歧，直接返回具体的 `failed / not_equivalent`（避免多周期时序 bug 因展开步数不足被掩盖为 `unproven`）；若仿真通过则仍保持保守的 `unproven`，不误报为形式等价。

## 结果契约

`verify` 返回 JSON-compatible 字典，包含：

| 字段 | 含义 |
| --- | --- |
| `status` | `success`、`failed`、`error` 或 `timeout` |
| `equivalent` | 成功为 `true`，确认不等价为 `false`，工具错误/超时为 `null` |
| `error_type` | 例如 `not_equivalent`、`syntax_error`、`interface_mismatch`、`missing_top`、`unproven`、`unsupported`、`tool_error`、`timeout`、`missing_observation` |
| `error_log` | 面向 A/D 反馈的精简诊断摘要（如 SAT 反例信号、报错行或 VCD 首个分歧时刻） |
| `log_path` | 完整工具日志路径 |
| `verification_method` | 例如 `yosys-formal`、`iverilog-regression`、`yosys-formal+iverilog-regression` |
| `proof_level` | 例如 `formal`、`bounded-formal`、`bounded-simulation`、`formal+bounded-simulation` |
| `is_mock` | 真实工具为 `false`，可控假工具/模拟为 `true` |
| `elapsed_seconds` | 本次验证耗时（秒） |

`success` 只在后端明确报告证明完成或回归波形一致时产生；语法错误、端口不匹配、缺少顶层、unproven、unsupported、空成功码或超时都会保持 `equivalent=null`，避免把工具异常误判为等价或不等价。

## 与其他任务联调及真实工具验证状态

- 任务 A 只需把 golden/candidate RTL 路径和配置传给 `verify`（或通过 CLI 调用）并读取返回字典；即使输入校验提前失败也会写入 `run_metadata.json`、`verify.log` 和 `verify_result.json`。
- 已在 **WSL2（Yosys 0.71+101 + Icarus Verilog 12.0 + VVP）** 完成对课程助教更新的**全部 8 个公开测试用例**（`case1`–`case8` 及其预置激励 `case1_tb.v`–`case8_tb.v`）的 `formal` + `simulation`（`both` 模式）端到端验证，全部通过且总耗时约 1.6 秒；同时在 `run_metadata.json` 中自动记录实际工具版本（`tool_versions`），覆盖结构重写、不等价反例、多周期时序 bug、端口不匹配、语法错误和超时场景。
- 建议团队尽快将这 8 个公开用例及统一配置同步导入本仓库的 `benchmarks/public/` 与 `configs/`，以便 A/B/C/D 全链路联调复用。
