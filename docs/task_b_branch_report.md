# Task B 分支说明

分支名称：`task-b-verification`

本分支包含任务 B（验证模块）的完整实现、真实 WSL2 工具链（Yosys 0.71+101 + Icarus Verilog 12.0）端到端测试，以及与 A/C/D 联调对齐约定。

## 已实现与已修复功能

- 提供 `src.verification.verify()`（Python 函数入口，第 3 参数 `config` 同时兼容 `VerificationConfig` 与普通 `dict`）、`python -m src.verification`（CLI 入口）和 `VerificationConfig`（验证配置对象）。
- **组合形式验证（两阶段）**：第一阶段采用 `equiv_make` + `equiv_struct -icells` + `equiv_simple -undef` + `equiv_status -assert`（亚秒级通过 `case4` `div_16bit` 等大型组合电路）；若仍有未证明单元则自动进入第二阶段 `miter -equiv` + `sat -verify`（双引号路径 + `-l` 落盘日志 + `-s` 脚本执行），支持跨架构重写证明并输出精确 SAT 反例信号表。
- **时序形式验证**：在 `proc; flatten;` 后加入 `async2sync` 兼容异步复位寄存器（`$adff`），运行 `equiv_struct -icells` + 有限步 `equiv_simple/equiv_induct` + `equiv_status -assert`（标记 `bounded-formal`）；遇到未证明 `$equiv` 时在剩余超时内追加有界 `miter + sat -seq` 反例搜索（支持 `reset` / `reset_active_low`）。
- **日志分类 Bug 修复**：修复旧版对 Yosys 0.52 日志中 `"Found 0 unproven $equiv cells"` / `"0 are unproven"` 误判为 `error / unproven` 的问题，并细分 `not_equivalent`、`syntax_error`、`interface_mismatch`、`missing_top`、`unproven`、`unsupported`、`tool_error`、`timeout`。
- **仿真回归增强**：支持替换 `__VCD__`、`` `VCD_PATH ``、以及 `opti_demo` 激励中的 `__SEED__`；修复 VCD 别名信号覆盖、按 IEEE 1364 规范扩展位宽、折叠同时间戳零延时 delta 周期毛刺，并在波形不一致时精确报告首个分歧时刻与信号值。
- **面向 D 的精简反馈与公共字段对齐**：提炼简洁 `error_log`（时序反例自动定位首个 `trigger=1` 失败周期）控制 Token 消耗；补充 `is_mock`、`elapsed_seconds` 与 `run_metadata.json` 中的 `tool_versions` 自动记录；`both` 模式在形式验证 `unproven` 时自动用仿真兜底捕获多周期 bug；输入校验提前失败也统一落盘 `run_metadata.json`。
- 不修改 golden RTL，每次运行使用独立目录保存脚本、完整日志、元数据和 JSON 结果；测试临时目录改为系统临时目录，不再在仓库根目录遗留 `.test-tmp/`。

## 本地运行命令（WSL2 / Linux）

在仓库根目录执行：

```bash
python3 -m compileall -q src/verification tests/verification
python3 -m unittest discover -s tests/verification -p "test_*.py" -v
```

当前测试覆盖 30 项用例（含单元测试与真实 Yosys 0.71+101 / Icarus Verilog 12.0 端到端测试），覆盖：

- **课程全部 8 个公开用例**（`case1` `barrel_shifter`、`case2` `fp_rounding`、`case3` `fixed_point_subtractor`、`case4` `div_16bit`、`case5` `verified_accu`、`case6` `LIFObuffer`、`case7` `verified_adder_64bit`、`case8` `verified_radix2_div`）及配套 `case1_tb.v`–`case8_tb.v` 的 `both` 模式端到端验证；
- 组合跨架构重写等价（如 `barrel_shifter` 行为级重写、`addsubz` 纹波进位改写）与 SAT 反例提取；
- 端口不匹配（`interface_mismatch`）、语法错误（`syntax_error`）、缺失顶层（`missing_top`）、超时（`timeout`）；
- 时序异步复位等价（`bounded-formal`）与时序 bug 反例检测；
- `simulation` 波形分歧时间戳报告与 CLI 入口调用。

## 调用样例

```python
from src.verification import VerificationConfig, verify

result = verify(
    golden_rtl="benchmarks/public/case3/golden.v",
    candidate_rtl="runs/case3/iter_001/candidate.v",
    config=VerificationConfig(
        top="top",
        mode="formal",
        timeout_seconds=120,
        run_dir="runs/case3/iter_001/verify",
    ),
)
print(result)
```

或命令行直接运行：

```bash
python3 -m src.verification golden.v candidate.v --top TopModule --mode both \
  --testbench stim_addsubz.v --observe out --observe result_is_zero \
  --run-dir runs/verify_demo
```

## 尚未完成（待团队配合）

1. 课程 8 个公开 benchmark RTL 源码及配套约束尚未导入 `benchmarks/public/`，导入后需补充全部 8 个用例（特别是 4 个时序用例）的回归配置与基线验证记录。
2. 尚未与 A 主控、C 评估完成真实全链路合入联调（本分支已具备提交 PR 合入 `main` 的条件）。
3. 复杂组合电路（如 `div_16bit`）与长周期时序电路（如 `verified_radix2_div`、`LIFObuffer`）的验证超时预算与 `formal/simulation` 组合策略需拿到真实源码后实测调优。
