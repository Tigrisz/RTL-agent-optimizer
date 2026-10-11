# RTL 自动优化 Agent 大作业

四人分工与一个月实施计划。团队规模：4 人；实施周期：约 4 周。

## 仓库结构与开发起步

当前仓库提供基础目录、配置模板和接口草案，尚未实现候选生成、验证、评估或完整 Agent 运行入口。

```text
RTL-agent-optimizer/
├── README.md
├── requirements.txt       # 框架确定后补充实际 Python 依赖
├── .gitignore
├── .env.example           # 模型配置模板
├── tools.env.example      # WSL 工具与库路径模板
├── src/
│   ├── controller/        # A：主控与集成
│   ├── verification/      # B：等价验证
│   ├── evaluation/        # C：综合与性能评估
│   └── optimization/      # D：候选生成与反馈策略
├── tests/                 # 模块测试与联调
├── benchmarks/public/     # 待导入课程公开原始 RTL
├── configs/               # 待确认的统一配置与约束
├── experiments/           # 精选候选、摘要与复现说明
└── docs/
    ├── interfaces.md      # 第一周接口草案
    └── weekly/            # 周计划与会议纪要模板
```

基础工具安装完成后，在 WSL / Ubuntu 中执行：

```bash
git clone https://github.com/Tigrisz/RTL-agent-optimizer.git
cd RTL-agent-optimizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
cp tools.env.example tools.env
```

填写本地配置；基础骨架尚不会自动加载这些文件。requirements.txt 当前只有说明，确定框架后由负责人添加经过验证的依赖版本。
真实 API Key、机器路径及临时运行输出不提交；精选实验按 [实验记录说明](experiments/README.md) 整理。

开始开发前，全组确认 [接口约定](docs/interfaces.md) 和 [统一配置清单](configs/README.md)。
每项任务从最新 main 创建独立分支，通过 PR 说明修改与实际验证后合并；公共接口变化提前通知相关成员。
周计划与周会记录使用 [模板](docs/weekly/template.md)。

| 项目目标<br>搭建自动化 RTL 优化 Agent：输入原始 RTL，生成候选实现，完成等价性验证及综合评估，在满足延时要求的前提下尽量缩小面积；通过多轮反馈迭代，输出最优有效 RTL 与评估报告。具体大模型暂不预设。 |

## 环境配置

建议全组统一使用 **WSL2 + Ubuntu + VS Code**。课程要求未限定必须使用 Linux，但当前课程 Demo 使用 Linux 环境与 Shell 脚本；采用 WSL 可以在 Windows 上运行这套工具链。

### 所需工具

| 工具或配置 | 用途 | 配置说明 |
| --- | --- | --- |
| WSL2 + Ubuntu | 提供 Linux 运行环境 | Windows 用户推荐使用；已有 Linux 环境可直接使用 |
| VS Code + WSL 扩展 | 编辑、调试和运行项目 | VS Code 安装在 Windows，通过微软 WSL 扩展连接 Ubuntu |
| Python 3 | 主控、工具调用和模型 API 调用 | 安装在 WSL 内；全组统一版本及依赖 |
| Git | 代码协作与版本管理 | 在 WSL 内克隆和维护仓库 |
| Yosys | RTL 综合与等价验证 | 全组统一版本和脚本配置 |
| Icarus Verilog（iverilog、vvp） | 仿真及课程 Demo 的波形比对 | 使用当前 Demo 时需要安装 |
| 标准单元库（.lib） | 工艺映射及面积评估 | 可参考 Demo 的 Nangate45；最终按课程评估要求统一库文件 |
| 模型 API | RTL 分析、候选生成及反馈修改 | 配置课程提供的 DeepSeek API 或最终选定的模型服务 |
| Agent 框架 | 组织工具调用与优化循环 | 选择 OpenCode 或 LangGraph 等方案；依赖按所选框架安装 |

### 1. 连接 VS Code 与 WSL

1. 在 Windows 安装 WSL2 和 Ubuntu，并完成 Ubuntu 用户初始化。
2. 在 Windows 安装 VS Code 和微软的 **WSL** 扩展。
3. 打开 Ubuntu 终端，在 Ubuntu 用户目录下克隆项目仓库，进入项目目录。
4. 执行 `code .` 打开 VS Code，确认左下角显示 WSL 连接状态。
5. 后续通过该窗口中的 WSL 终端安装依赖和运行项目。

建议代码放在 Ubuntu 用户目录下，例如 `~/projects/`。Python、Yosys 等运行工具应安装在 WSL 内。

### 2. 安装基础工具

以下命令在 **Ubuntu / WSL 终端**中运行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip yosys iverilog wget
```

检查工具是否可用：

```bash
git --version
python3 --version
yosys -V
iverilog -V
vvp -V
```

在项目目录中创建 Python 虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

课程 Demo 的调度脚本使用 Python 标准库；采用其他 Agent 框架后，再安装相应依赖。确定依赖后，统一维护依赖清单，记录 Python、Yosys、仿真工具版本和 Demo 提交版本。不同安装渠道的 Yosys 版本可能不同，后续评估应使用统一版本。

### 3. 配置标准单元库与工具路径

按课程评估要求或 Demo 说明获取 `.lib` 文件。全组使用同一份标准单元库，并统一综合命令、时序约束和指标单位。

使用课程 Demo 时，从 `tools.env.example` 复制出本地 `tools.env`，配置工具与库文件的绝对路径，例如：

```dotenv
YOSYS_BIN=/usr/bin/yosys
LIB_FILE=/home/<用户名>/edatools/NangateOpenCellLibrary_typical.lib
```

以上为示例，需替换为实际路径；若使用其他方式安装 Yosys，应填写对应可执行文件路径。

### 4. 配置模型与 Agent 框架

确定 Agent 框架及模型调用方式，配置 API 地址、模型名、API Key、请求超时和运行预算。使用 Demo 的自定义模型后端时，可从 `.env.example` 创建 `.env`，按实际服务填写配置：

```dotenv
LLM_BACKEND=custom
LLM_BASE_URL=<实际 API 地址>
LLM_API_KEY=<实际 API Key>
LLM_MODEL=<实际模型名>
```

具体字段和请求格式以所使用代码及服务说明为准。API Key 仅放在本地环境变量或本地配置文件中，不提交仓库；仓库保留不含密钥的配置模板。

建议在 `.gitignore` 中至少加入：

```gitignore
.venv/
.env
tools.env
__pycache__/
*.pyc
```

### 5. 统一验证与评估口径

当前 Demo 使用 Icarus Verilog 仿真和波形比对进行功能检查，性能报告包含面积及逻辑深度 `ltp`。仿真通过不等于完整的形式等价证明，逻辑深度也不能直接作为纳秒延时。

B / C 在第一周确认课程最终采用的验证方式、延时定义、标准单元库和约束；必要时向老师确认，并将统一配置记录在仓库中。环境配置、接口设计及模块原型开发可并行推进，进度仍按下文分工与里程碑执行。

配置参考：

- [课程 Demo 与依赖说明](https://github.com/alex00153/opti_demo)
- [VS Code 连接 WSL](https://code.visualstudio.com/docs/remote/wsl)
- [Yosys 安装说明](https://yosyshq.readthedocs.io/projects/yosys/en/latest/getting_started/installation.html)

## 项目工作流程

原始 RTL → 候选 RTL 生成 → 等价性验证（失败返回修复）→ 综合与面积/延时评估 → 收敛判断（未收敛继续迭代）→ 最佳 RTL 与报告

实施原则：工具执行与日志解析由程序完成；验证通过后再评估性能；全程保存“原始版本”和“历史最佳有效版本”，避免迭代导致结果退化。

## 四人分工及交付成果

| 成员 | 负责子系统 | 主要任务与边界 | 阶段性交付与验收 |
| --- | --- | --- | --- |
| A | Agent 框架与集成 | 主程序、模块调用、优化循环、停止/收敛判断、最优版本管理、异常状态和最终输出；不代写 B/C/D 的模块。 | 可以自动调度候选生成→验证→评估；正确记录每轮状态，并输出最佳有效 RTL。 |
| B | 等价性验证与正确性测试 | Yosys 等价验证；组合/时序用例的正确性回归；区分不等价、运行错误、超时；提炼验证日志。 | 独立提供 verify 接口、回归测试及失败分类；验证结果可复现。 |
| C | 综合与性能评估 | Yosys 综合、面积/延时数据提取、延时约束判断；基线对比、批量评估、指标汇总和评分统计。 | 独立提供 evaluate 接口；统一配置输出可比较的面积/延时报告。 |
| D | RTL 优化与反馈策略 | 分析 RTL；设计优化策略和候选生成接口；根据不等价日志或性能反馈调整策略、避免无效重复尝试。 | 独立提供 optimize 接口；至少实现多轮候选生成与反馈驱动的改进流程。 |

均衡原则：B 承担正确性回归，C 承担性能批量测试，D 专注优化策略；A 承担总控与集成。四人分别撰写自己负责部分的报告，避免测试与文档工作集中到一人。

## 四周并行开发安排

第一周共同熟悉课程 Demo 与 Yosys；之后模块并行推进，从第二周开始持续集成，而不是等到最后集中合并。

| 阶段 | A：主控 | B：验证 | C：评估 | D：优化 |
| --- | --- | --- | --- | --- |
| 第 1 周<br>理解与起步 | 学习全链路；确定项目结构、接口及主流程骨架。 | 熟悉 Yosys 验证；完成简单组合电路的验证示例。 | 熟悉综合及评估输出；跑通原始 RTL 基线评估。 | 熟悉 8 个公开用例；整理优化策略并生成首批候选。 |
| 第 2 周<br>基础闭环 | 连接 B/C/D；实现一次完整调用与结果保存。 | 完成 verify 接口；接入日志和异常分类。 | 完成 evaluate 接口；接入面积/延时提取。 | 完成 optimize 初版；支持基于反馈再生成候选。 |
| 第 3 周<br>联合改进 | 多轮迭代、停止条件、最佳版本保存、状态记录。 | 组合/时序正确性回归；排查验证失败。 | 性能对比、批量运行、统一评估配置。 | 改进优化策略；分析无收益及失败案例。 |
| 第 4 周<br>验收交付 | 联调、运行说明、最终代码集成。 | 完成回归验证结果与模块文档。 | 完成公开用例性能汇总与图表/评分统计。 | 完成策略对比、优化案例与分析记录。 |

## 关键里程碑与验收标准

| 时间 | 里程碑 | 可检查的验收条件 |
| --- | --- | --- |
| 第 7 天 | 模块原型可独立运行 | 四人均能展示输入、处理、输出；公开用例至少各跑通一项相关功能。 |
| 第 14 天 | 完整 Flow 首次跑通 | 至少一个公开用例完成“生成—验证—评估—输出”，并有可追溯运行记录。 |
| 第 21 天 | 多轮自动优化稳定运行 | 有失败反馈、收敛/停止判断、最佳版本保存；覆盖组合与时序两类。 |
| 第 28–30 天 | 最终测试与提交 | 运行公开用例，汇总面积/延时、运行时间和模型消耗；整理代码、结果及方案报告。 |

## 项目优先级与测试范围

课程材料给出 8 个公开用例（4 个组合、4 个时序）及 4 个后续隐藏用例。评分涵盖流程搭建、公开组合与时序电路优化、Hidden Case 和方案报告。

| 优先级建议<br>① 完整 Flow 稳定可运行  →  ② 等价性可信、评估口径一致  →  ③ 公开用例获得正向优化收益  →  ④ 扩展到时序与未知用例，并控制迭代运行成本。 |
| --- |

## 统一接口与集成约定

第一周必须确定接口格式，A 可先使用模拟返回值开发主控，B/C/D 使用独立样例联调。下列为建议接口，并非课程规定。

| 模块 | 建议接口 | 返回内容 |
| --- | --- | --- |
| D → A | optimize(current_rtl, feedback) | 候选 RTL 路径/文本、采用的策略、生成状态 |
| B → A | verify(golden_rtl, candidate_rtl) | equivalent、status、error_type、error_log |
| C → A | evaluate(rtl, constraints) | area、delay、timing_met、status、report_path |
| A → 记录 | iteration_record(...) | 迭代编号、候选版本、等价性、性能变化、耗时、最终决策 |

数据约定：统一路径规范、面积及延时单位、时序约束、综合配置和错误码；每轮留存候选文件、验证日志、性能报告，保证结果可复现。

## 协作机制

- 统一 Git 仓库：每人独立分支，完成最小测试后合并；接口变更应提前告知所有成员。

- 固定沟通节奏：每周同步进度，群内随时交流。

- 持续集成：第二周起每周至少完成一次主程序联调，不允许月底才首次整合。

- 可复现测试：B/C 分别维护正确性与性能回归，D 提供候选与策略说明，A 汇总运行日志。

- 文档同步维护：四人分别编写各自模块设计、实现、测试与问题总结；A 负责最终统一格式。


## 统一验收口径

最终系统能自主生成候选 RTL、验证等价性、综合评估、依据反馈迭代，并输出历史最佳有效 RTL 及可复现报告；模型可替换，工具链和控制接口尽量保持稳定。

说明：项目目标、基本 Flow、工具链、公开/隐藏测试与评分框架来源于课程《大作业.pdf》（第 1–4 页）；人员分工、进度、接口和协作规则为本组建议实施方案，可根据实际开发情况调整。

