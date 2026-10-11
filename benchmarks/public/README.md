# 公开用例

这里保存课程允许团队共享的公开用例原始 RTL；当前尚未导入课程文件。
导入时记录课程来源、版本、顶层模块、依赖文件、参数和必要约束。
原始 RTL 不作为优化输出覆盖；候选写入本地 runs/ 或精选实验目录。

| 用例 | 类型 | 模块名 |
| --- | --- | --- |
| case1 | 组合 | barrel_shifter |
| case2 | 组合 | fp_rounding |
| case3 | 组合 | fixed_point_subtractor |
| case4 | 组合 | div_16bit |
| case5 | 时序 | verified_accu |
| case6 | 时序 | LIFObuffer |
| case7 | 时序 | verified_adder_64bit |
| case8 | 时序 | verified_radix2_div |

B/D 核对功能语义；C 记录基线与评估配置。用例名称来自项目现有 README，行为细节以实际课程源码为准。
