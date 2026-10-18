# 2026-10-17：D 独立生成实验快照

来源为 [opti_demo](https://github.com/alex00153/opti_demo) 的公开示例，原始 MIT 授权见 [UPSTREAM_LICENSE](UPSTREAM_LICENSE)。
不是课程要求的 8 个公开用例。此目录保存确切输入快照；上游版本未固定到 commit，不将可变 main 作为唯一复现依据。

实际请求模型为 deepseek-v4-pro，关闭 thinking，单次最多输出 2048 token；本次 3 个请求均成功，共 1703 token。

| 输入 | 轮次 | 策略 | token | 事后检查 | 反馈 |
| --- | --- | --- | --- | --- | --- |
| popcount3 | 1 | area_simplify | 448 | 仅删除注释，与输入 token 相同 | 无 |
| addsubz | 1 | area_simplify | 541 | 原样返回 | 无 |
| addsubz | 2 | timing_restructure | 714 | 表达式发生变化，尚未验证 | 人工模拟时序违规 |

查看 [evidence.json](evidence.json) 获取真实 run_id、用量、耗时、反馈和 token 指纹审计。
其中初始 is_duplicate 是当时版本的输出；post_run_audit 是增强去重后离线复核，不改写原始生成历史。
路径已为此快照改成相对路径；原始运行记录仍保存在本地被忽略的 runs/ 目录。

每项候选为 `<case>_r<round>.v`，对应实际提示词为 `<case>_r<round>_prompt.md`。
`*_original.v` 是未修改输入；`*_context.json` 是调用上下文；模拟反馈单独保存在 simulated_timing_feedback.json。

可在项目根目录用本快照离线检查保存流程：

```bash
python -m src.optimization experiments/demo_2026-10-17/addsubz_original.v --backend mock --context experiments/demo_2026-10-17/addsubz_context.json --history runs/meeting/history.jsonl
```

改成 `--backend custom` 将产生新的一次付费模型请求；模型输出不保证与本快照相同。
候选均没有经过 HDL 编译、仿真、形式等价或综合性能测量，不能据此宣称面积或延时改善。
