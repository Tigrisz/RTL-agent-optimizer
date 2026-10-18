# Task B 分支说明

分支建议名称：`task-b-verification`

本分支包含任务 B（验证模块）的独立实现，以及与 A/C/D 联调前的输入责任和交付约定。

## 已实现功能

- 提供 `src.verification.verify()`（统一验证函数）和 `VerificationConfig`（验证配置对象）。
- 使用 Yosys 执行组合 RTL 的形式等价验证。
- 支持顺序 RTL 的有限步检查，并将成功结果标记为 `bounded-formal`。
- 使用 Icarus/VVP 执行可选的仿真回归，比较显式指定的 `observed_outputs`（观测输出）。
- 支持 `formal`、`simulation` 和 `both` 三种模式。
- 区分 `success`、`failed`、`error`、`timeout`，工具错误和超时返回 `equivalent: null`。
- 支持多文件 RTL、include 目录、宏定义、工具路径和超时时间。
- 保存 `run_metadata.json`、Yosys 脚本、编译/运行日志、VCD 波形和 `verify_result.json`。
- 不修改 golden RTL（基准 RTL），每次运行使用独立目录。
- 新增任务 B 联调对齐说明：`docs/task_b_alignment.md`。

## 本地运行命令

在仓库根目录执行：

```bash
python -m unittest discover -s tests/verification -p "test_*.py" -v
python -m compileall -q src/verification tests/verification
```

当前测试结果：

```text
Ran 16 tests
OK
```

真实验证调用示例：

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

## 输入和输出样例

### 等价验证成功

输入：

```text
golden_rtl    = benchmarks/public/case3/golden.v
candidate_rtl = runs/case3/iter_001/candidate.v
mode          = formal
top           = top
```

输出：

```json
{
  "status": "success",
  "equivalent": true,
  "error_type": null,
  "error_log": null,
  "log_path": "runs/case3/iter_001/verify/yosys.log",
  "verification_method": "yosys-formal",
  "proof_level": "formal"
}
```

### 确认不等价

```json
{
  "status": "failed",
  "equivalent": false,
  "error_type": "not_equivalent",
  "error_log": "counterexample found; outputs mismatch",
  "log_path": "runs/case3/iter_001/verify/yosys.log"
}
```

### 工具错误或超时

```json
{
  "status": "timeout",
  "equivalent": null,
  "error_type": "timeout",
  "error_log": "simulation timeout",
  "log_path": "runs/case3/iter_001/verify/candidate_run.log"
}
```

`error_log`（错误摘要）用于主控快速反馈；`log_path`（完整日志路径）指向保留全部命令、标准输出和标准错误的日志文件。

## 尚未完成的部分

1. 尚未在真实课程 benchmark 上完成组合和时序端到端验证。
2. 尚未完成 A 主控、C 评估、D 候选生成与 B 的真实全链路联调。
3. 顺序验证的 clock/reset（时钟/复位）目前记录在元数据中，尚未根据最终用例生成完整的形式约束。
4. `docs/interfaces.md` 中要求的 `is_mock: true` 字段尚未加入正式返回结果，需要与 A 确认模拟工具结果的协议。
5. 真实 benchmark 的顶层模块、额外源文件、testbench 和 `observed_outputs` 尚未统一登记。

## 当前阻塞

- 当前没有把假工具测试结果当作真实 Yosys/Icarus 证明；真实工具链可用后还需要重新执行 smoke test（冒烟测试）和 benchmark 回归。
