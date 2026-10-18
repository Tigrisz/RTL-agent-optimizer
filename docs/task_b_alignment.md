# 任务 B 联调对齐清单

本文说明任务 B（验证模块）在与 A（主控）、C（评估）和 D（优化）联调前需要确认的输入、提供方、时间节点和交付结果。Demo 只作为最小闭环参考；实际联调以本项目接口和真实工具输出为准。

## 1. B 的边界与当前交付

B 接收一个不可修改的 golden RTL（基准 RTL）和一个待检查的 candidate RTL（候选 RTL），执行形式验证或仿真回归，并返回统一 JSON 结果。B 不负责生成 candidate，不负责综合面积/延时，也不负责决定是否保留候选。

当前已经提供：

- `src/verification.verify`（统一验证入口）；
- `VerificationConfig`（验证配置对象），支持顶层、多文件源、include 目录、宏定义、工具路径、超时、testbench（测试平台）、观测输出、clock/reset（时钟/复位）信息；
- Yosys 形式等价后端；
- Icarus/VVP 仿真回归后端；
- `success`、`failed`、`error`、`timeout` 状态和 `not_equivalent`、`tool_error`、`timeout` 等错误分类；
- 每轮独立运行目录、Yosys 脚本、完整工具日志、运行元数据和 JSON 结果；
- 16 项模块测试，覆盖接口、超时、结果分类、脚本生成和 VCD 比较。

## 2. 联调前必须冻结的公共信息

下列信息应由全组或 benchmark 负责人统一确认，并写入配置文件或联调记录：

| 信息 | 需要谁确认 | 具体内容 |
| --- | --- | --- |
| 原始 RTL | benchmark 负责人/A | golden RTL 的绝对路径；不得被候选覆盖 |
| 顶层模块 | A、B、C、D 共同确认 | `top` 名称、参数和实例入口 |
| 源文件集合 | A、B、C 共同确认 | 主 RTL、额外 `.v/.sv` 文件、include 目录和宏定义 |
| 工具版本 | 全组/环境负责人 | Python、Yosys、Icarus、VVP 版本和可执行路径 |
| 组合/时序属性 | B 与 benchmark 负责人 | 是否 `sequential`、clock 名称、reset 名称、复位有效电平 |
| 仿真输入 | B 与 benchmark 负责人 | testbench、波形生成方式、仿真结束条件 |
| 比较信号 | B 与 benchmark 负责人 | `observed_outputs` 中的输出端口或层次化信号名称 |
| 超时口径 | A、B、C 共同确认 | 单次验证超时时间，超时后 A 如何记录和处理 |
| 运行目录 | A 与 B 确认 | A 是否为每轮提供唯一 `run_dir`，候选编号如何映射到目录 |

如果上述信息未确认，B 可以返回输入错误，但不能可靠地声称候选 RTL 等价或不等价。

## 3. 谁在什么节点提供什么

### 节点一：基线和配置冻结

**提供方：A、C、benchmark 负责人、全组环境负责人**

需要提供：

- 原始 golden RTL 路径；
- candidate 和 golden 的顶层模块名；
- 完整源文件列表、include 目录和宏定义；
- Yosys/Icarus/VVP 可执行路径或 `tools.env`；
- 组合/时序分类、clock/reset 信息；
- 仿真 testbench 和 `observed_outputs`；
- 默认 timeout（超时时间）；
- 每轮唯一候选编号和运行目录命名规则。

**B 拿到后交付：**

- 一份可复现的 `VerificationConfig` 示例；
- 一次 golden 对 golden 的验证记录；
- 工具版本、脚本格式和日志位置确认；
- 缺失字段时的明确错误类型。

### 节点二：D 生成候选后

**提供方：D，传递方：A**

D 需要把候选 RTL 写成一个明确的文件，并通过 A 传给 B：

```text
candidate_path       候选 RTL 绝对路径
candidate_id         候选编号
strategy             生成该候选采用的策略
top                  如与基线不同，需要显式说明
```

D 不需要解析 B 的 Yosys 日志。D 只需保证 candidate 文件可读、源文件完整、顶层接口没有未经说明的变化。

**B 拿到后交付：**

- 运行 `verify(golden_rtl, candidate_rtl, config)`；
- 写入独立运行目录；
- 返回 `verify_result.json`；
- 在 `error_type=not_equivalent` 时提供错误摘要和完整日志路径，供 A 传给 D；
- 在工具错误或超时时返回 `equivalent=null`，避免 D 把环境故障误认为优化失败。

### 节点三：B 通过后交给 C

**提供方：B，接收方：A/C**

只有 B 返回以下结果时，A 才应把 candidate 交给 C：

```json
{
  "status": "success",
  "equivalent": true
}
```

A 应将以下内容传给 C 或记录到迭代记录：

- candidate 路径和候选编号；
- golden 路径；
- B 的 `verify_result.json` 路径；
- `proof_level`（证明级别）；
- `run_metadata.json` 路径；
- B 的工具版本和源文件配置。

C 使用与 B 一致的顶层、源文件、宏定义和工具版本，才能保证评估结果可比较。B 不提供面积或延时结论。

### 节点四：B 失败后的反馈

**提供方：B，接收方：A/D**

A 根据状态分流：

| B 结果 | A 的处理建议 | 是否交给 C |
| --- | --- | --- |
| `success` + `equivalent=true` | 记录为有效候选 | 是 |
| `failed` + `not_equivalent` | 将摘要和日志传给 D 修复 | 否 |
| `error` | 检查输入、工具和脚本，必要时重试或终止本轮 | 否 |
| `timeout` | 按统一重试/终止策略处理，并记录耗时 | 否 |

工具错误和超时不是“不等价”，不能作为 D 的 RTL 错误反馈。

## 4. B 的调用和输出样例

### 形式验证

```python
from src.verification import VerificationConfig, verify

config = VerificationConfig(
    top="top",
    mode="formal",
    timeout_seconds=120,
    run_dir="runs/case3/iter_001/verify",
)

result = verify(
    golden_rtl="benchmarks/public/case3/golden.v",
    candidate_rtl="runs/case3/iter_001/candidate.v",
    config=config,
)
```

成功输出：

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

确认不等价时：

```json
{
  "status": "failed",
  "equivalent": false,
  "error_type": "not_equivalent",
  "error_log": "counterexample found; outputs mismatch",
  "log_path": "runs/case3/iter_001/verify/yosys.log"
}
```

仿真模式必须另外提供 `testbench` 和 `observed_outputs`。仿真通过只能说明当前 testbench 激励下波形一致，结果标记为 `bounded-simulation`，不替代完整形式等价证明。

## 5. 当前阻塞与未完成事项

1. 当前 Windows PATH/WSL 环境还没有完成真实 Yosys、Icarus/VVP 的端到端运行；现有 16 项测试使用可控假工具验证接口和分类逻辑。
2. 仓库中尚未导入最终公开 benchmark、真实 testbench、顶层模块和观测信号清单；这些信息需要 benchmark 负责人或 A 提供。
3. 顺序逻辑的 `clock`、`reset` 信息目前会进入运行元数据；真实时序约束和复位假设仍需结合课程用例确认。
4. A/C/D 尚未完成一次真实全链路联调；当前 B 可以独立调用，但还没有接入最终主控和评估流程。
5. 在真实工具和 benchmark 确认后，需要补充至少一组组合样例、一组时序样例、一个不等价样例、一个工具错误样例和一个超时样例。

## 6. 联调验收条件

任务 B 可以交付联调的最低条件是：

- A 能传入绝对路径和完整配置，并得到 JSON 字典；
- golden RTL 在运行过程中不被修改；
- B 能区分成功、不等价、工具错误和超时；
- 每轮有唯一运行目录和完整日志；
- C 能复用 B 确认过的源文件、top 和工具配置；
- D 能根据 `not_equivalent` 摘要和日志继续生成候选；
- 至少一个真实组合用例和一个真实时序用例完成端到端验证。

## 7. 当前实现的联调注意事项

- 当前入口是 Python 函数 `verify()`（验证函数），没有独立命令行入口；A 需要在 Python 主控中调用它。
- `top`（顶层模块名）最好由 A 显式提供。自动识别只适用于简单单模块文件，多模块设计不能依赖“第一个 module”猜测。
- `simulation`（仿真回归）不会自动重命名顶层模块；golden、candidate 和 testbench 的顶层接口需要保持兼容。如果候选改变模块名或接口，D/A 必须提供 wrapper（包装模块）或明确映射。
- `clock`、`reset` 和 `reset_active_low` 目前会记录在 `run_metadata.json`，但不会自动生成完整的时钟/复位形式约束；时序语义仍需由实际 RTL 和 testbench 表达。
- `log_path`（完整日志路径）会根据后端指向具体日志，例如 `yosys.log` 或 `candidate_run.log`；A 应读取该字段，不要假设固定叫 `verify.log`。所有其他日志仍保留在同一 `run_dir`。
- 公共接口草案要求 mock（模拟工具）结果带 `is_mock: true`。当前实现的单元测试使用假工具，但正式 `verify()` 结果尚未增加 `is_mock` 字段；如果 A 要在主控中运行模拟后端，需要先统一这一字段的协议。
- 输入检查过早失败时，可能只生成 `verify.log` 和 `verify_result.json`，还没有 `run_metadata.json`。A 如果要求每轮都有完整元数据，应在主控侧先生成迭代记录，或后续统一 B 的错误路径。
- `run_dir`（运行目录）默认使用 UTC 时间戳和随机后缀。A 应显式传入包含 `case_id` 和 `iteration` 的目录，确保候选、日志和 C 的评估报告可以对应起来。
