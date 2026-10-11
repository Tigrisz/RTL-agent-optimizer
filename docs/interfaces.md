# 模块接口约定（第一周草案）

本文件扩展 README 的建议接口，供 A/B/C/D 在第一周确认；当前尚无接口实现。
更改公共字段前，在 PR 中说明影响并通知相关负责人。

## 共同约定

- 调用采用 Python 函数，返回可 JSON 序列化的字典。
- RTL 输入采用文件路径；顶层模块、参数、多文件依赖等上下文由 A/B/C/D 在接入时共同补充约定，不依靠模糊猜测。
- 运行时路径由 A 解析为绝对路径；提交到仓库的文档和精选实验使用仓库相对路径。
- 每轮分配唯一候选编号，保存候选、验证日志和评估报告，不覆盖原始 RTL。
- 通用状态为 `success`、`failed`、`error`、`timeout`；不得将工具错误或超时归为不等价。
- 未知或不适用的值使用 `null`，不能以 0 或 false 代替缺失结果。
- 模拟结果额外标注 `is_mock: true`；主控不得将其作为真实验证/评估证据。

## D：候选生成

`optimize(current_rtl, feedback)`

首次调用 `feedback` 可为 null。后续反馈由 A 汇总验证、性能与近期策略，避免重复发送完整历史。

```json
{
  "status": "success",
  "candidate_path": "<绝对路径>/runs/case3/iter_001/candidate.v",
  "strategy": "本轮采用的优化策略",
  "error_type": null,
  "error_log": null
}
```

候选尚未经过等价验证。生成失败时 candidate_path 为 null；API 异常、空输出和输出格式问题应提供明确 error_type。
反馈应包含可用的 verify/evaluate 结果、基线、已尝试策略和候选标识；具体历史长度由 A/D 确定。

## B：等价验证

`verify(golden_rtl, candidate_rtl)`

```json
{
  "status": "success",
  "equivalent": true,
  "error_type": null,
  "error_log": null,
  "log_path": "<绝对路径>/runs/case3/iter_001/verify.log"
}
```

- 确认等价：success / equivalent=true。
- 确认不等价：failed / equivalent=false / error_type=not_equivalent。
- 工具报错或超时：error 或 timeout / equivalent=null，返回错误分类与摘要。
- 验证方式及其适用范围必须随运行配置记录；仿真通过不能直接当作完整形式等价证明。

golden_rtl 始终指向原始用例。完整日志保留在 log_path，error_log 用于简短反馈摘要。

## C：综合与性能评估

`evaluate(rtl, constraints)`

constraints 需引用统一配置，包含顶层、参数和源文件等评估上下文，并在确认后提供延时上限与单位。

```json
{
  "status": "success",
  "area": null,
  "area_unit": null,
  "delay": null,
  "delay_unit": null,
  "timing_met": null,
  "report_path": "<绝对路径>/runs/case3/iter_001/evaluate.json",
  "error_type": null,
  "error_log": null
}
```

以上 null 为字段占位，不代表已有真实评估结果。完成真实评估后，success 必须提供该评估口径要求的有效数值和单位；缺失必需指标时返回 error。
若课程口径暂未确认，明确记录未确认状态，不能虚构物理延时或判定 timing_met=true。
评估执行成功但违反延时约束时，status=success、timing_met=false；它不能成为满足约束的最优候选。
原始基线与候选必须使用相同库、约束、工具版本与综合配置。

## A：调度与迭代记录

候选生成 → B 验证 → 通过后 C 评估 → 判断是否保留 → 将反馈传给 D。
原始 RTL 基线可独立评估。主控分别处理不等价、错误、超时、约束不满足和无收益。

每轮至少记录：用例 ID、迭代编号、候选路径与策略、模块状态、验证结果、性能与单位、配置版本、耗时和最终决策。
保留原始版本与历史最佳有效版本；只有真实验证通过且满足已确认约束的候选，才可参与最佳版本更新。
