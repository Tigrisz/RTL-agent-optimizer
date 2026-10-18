# D：独立候选生成与反馈处理模块

从仓库根目录运行，使用 Python 3.10+ 标准库，无新增依赖：

```bash
python -m src.optimization tmp/opti_demo/case/bench/popcount3/popcount3_v1_behavioral.v --backend mock
python -m unittest discover -s tests -p test_optimization.py -v
```

命令向 stdout 输出 JSON；success 退出码为 0，其他结果为 1。候选保存至
`runs/optimization/<uuid>/candidate.v`（SystemVerilog 使用 .sv），返回绝对路径。
每次调用创建新目录，不覆盖输入。mock 明确返回 `is_mock: true`，只复制输入源码以检查流程。

真实调用：复制根目录 `.env.example` 为 `.env`，填写 `LLM_BACKEND=custom`、
`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 和 `LLM_TIMEOUT_SECONDS`。
base 必须为 HTTPS API 前缀，例如服务需要 `/v1` 时应包含该路径；程序追加 `/chat/completions`。
采用非流式 JSON 请求，读取 `choices[0].message.content`，其他协议需要额外适配。
进程环境变量逐项覆盖本地文件；支持简单 KEY=VALUE 和成对引号，不展开变量或执行 shell。
不自动从真实后端回退 mock，不重试；一次调用最多发起一个模型请求，不跟随重定向。
`LLM_MAX_TOKENS` 控制单次输出上限（64..8192，默认 2048）；触及上限返回 output_truncated，不保存截断候选。
DeepSeek 使用 `LLM_THINKING=disabled`，保持模型为 deepseek-v4-pro；其他服务不支持此参数时将该项删除。

```bash
python -m src.optimization path/to/current.v --env-file .env --backend custom --feedback path/to/feedback.json
```

密钥只保存在环境变量或被 Git 忽略的本地 `.env` 中。程序不打印配置、密钥、原始响应或异常正文。
此入口只生成候选，不运行 Yosys、仿真或性能评估。

Python 接入：

```python
from src.optimization import optimize

result = optimize(current_rtl, feedback)  # 兼容原有两个位置参数，feedback 可为 None
# 可选：output_dir、env_file、backend、context、history_path
```

反馈示例（这些数值/状态仅用于说明格式，不是实验结论）：

```json
{
  "verify": {"status": "failed", "equivalent": false, "error_log": "位宽相关反例摘要"},
  "evaluate": null,
  "baseline": null,
  "tried_strategies": ["area_simplify"],
  "candidate_id": "iter_001"
}
```

策略优先级：明确不等价时 `repair_equivalence`；评估成功且时序不满足时
`timing_restructure`；否则在 `area_simplify`、`resource_share` 中选择未尝试策略。
再按未尝试顺序探索 arithmetic_restructure、control_simplify；全部尝试后回到保守简化。
策略均为待检验假设，不保证收益，不根据案例名称硬编码。
工具执行错误不会被当作不等价。反馈上限 64000 字符，进入 prompt 的长日志截断至 1500 字符，列表只保留最后 6 项。
完整 RTL 不截断；单文件源码超过 64000 字符时返回 input_error。

模板沿用 `tmp/opti_demo/prompts/rtl_optimize.md` 的面积优先、保持接口和单代码块要求，
在正式模块中扩展反馈与周期语义约束，不依赖 tmp 文件。不按案例名选择或硬编码提示词。
只接受一个 verilog/systemverilog 代码块，并检查 module/endmodule 成对；这不是语法解析、
完整性证明或功能验证。context 可记录参数与约束，但不会执行 elaboration、展开 include 或自动收集多文件依赖，不应直接用于复杂工程闭环。

2026-10-14 检查：7 项 unittest 通过，包含 HTTP 适配器模拟、反馈策略、错误分类、
候选隔离及原始源码保护；popcount3 示例通过显式 mock 完成保存。
当时本地真实调用返回 config_error。该历史状态已由下方 2026-10-17 真实生成记录更新。
候选未经过 B/C 验证评估，没有功能正确或性能提升结论。课程 8 个源码仍待提供。

## 2026-10-17：DeepSeek 接入检查

- 本地 `.env` 配置官方地址 `https://api.deepseek.com` 和模型 `deepseek-v4-pro`；密钥只保存在被 Git 忽略的本地配置。
- 固定短文本连通性检查成功，服务返回模型 `deepseek-v4-pro` 和 `OK`，共消耗 10 token。
- 本次连通性检查不发送 RTL 或项目文件；结果保存在本地 `runs/optimization/api_smoke_check.json`。
- 最初发送 Demo RTL 的测试被自动审批拒绝；用户随后明确授权，已完成下方真实生成测试。文本连通性与 RTL 生成分别记录。
- 后续仅更换密钥时，更新 `.env` 中的 `LLM_API_KEY`，保持模型与地址不变；如设置了同名进程环境变量，应同步更新，因为环境变量优先。

## 设计上下文、历史与调用记录

```python
result = optimize(
    current_rtl, feedback,
    context={"design_id": "example", "top": "TopModule", "parameters": {},
             "constraints": {"delay_limit": None, "delay_unit": None}},
    history_path="runs/example/history.jsonl",
)
```

- context 上限 8000 字符，原样传给模型；顶层、参数、周期及延时约束由调用者提供，未知值填 null。
- history_path 是单个串行会话的 JSONL；同 design_id、同 context、同真实/mock 后端才共享历史。design_id 未指定时使用输入绝对路径。
- 同一设计的后续输入路径变化时，应保持 design_id 与约束一致；不同设计或参数配置不要共用 design_id/context。
- 每轮保存 prompt.md、candidate.v/.sv 和 record.json；错误在输出目录可创建时也会留存记录。
- 返回额外字段包括 run_id、record_path、prompt_path、model、usage、elapsed_seconds、feedback_is_mock、candidate_hash、candidate_fingerprint、is_duplicate、duplicate_of。
- source/candidate_hash 用于文本追溯；fingerprint 忽略注释和排版并保留 token 边界，用于识别原样返回或重复代码，不是语义等价证明。
- is_duplicate=true 仍可返回 success，表示生成与保存完成；A 可跳过重复评估或切换策略。D 不自动追加付费请求。
- 近期最多 6 条生成摘要进入 prompt；历史文件本身持续保存。历史文件不提供并发锁，调用者应串行使用或每个设计分开文件。
- 本模块不管理全局最优版本或收敛停止，正式循环交给 A。

CLI 对应增加 `--context context.json --history runs/example/history.jsonl`。

## 独立演示与真实结果

```bash
# 仅复制输入、模拟反馈、无 API 消耗
python -m src.optimization.demo --backend mock

# 最多 3 次真实 API 请求，含一次明确标注的模拟时序反馈
python -m src.optimization.demo --backend custom
```

演示使用 tmp/opti_demo 下的 popcount3、addsubz，支持 `--demo-root` 指定其他 Demo 根目录。
它是 D 的开发演示入口，不是完整优化主控；每次从原始 RTL 生成，不将未经验证的候选提升为新的可信基线。

2026-10-17 已完成 3 次真实生成，共 1703 token：popcount3 首轮仅删除注释；addsubz 首轮原样返回；
addsubz 在模拟时序反馈后切换 timing_restructure 并生成另一写法。前两项由改进后的 token 指纹复核为无实质变化。
本次重跑共 17 项 unittest 通过，包含注释级重复检测、跨设计历史隔离、截断拒收、元数据与模拟反馈标记。
精选输入、候选、实际 prompt、token 和事后去重审计见 [实验快照](../experiments/demo_2026-10-17/README.md)。
这些结果只证明真实生成链路与反馈分支可工作，没有等价、面积或延时改善结论。
