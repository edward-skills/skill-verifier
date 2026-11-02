# Skill Verifier

当前版本：**0.3.4**。区分检查导出的 skill、在宿主内使用验证器，以及驱动另一个 agent 执行任务。[新版说明](docs/releases/v0.3.4.md)。下文的独立验收对应冻结的 0.3.2，后续改动使用单独的作者/CI 证据。

[全部 Skills](https://github.com/edward-skills) · [English](README.md) · [验证范围](docs/validation.md)

按真实任务契约检测 skill，保留可复查证据，给出修正建议和回归检查。可以先做本地脚本与产物 QA；模型对比需要另行配置和授权。

**仅调用使用。** 允许为自己或客户安装、调用并使用生成报告；不授权转售、再分发或发布修改版 skill。[完整许可](LICENSE.md)。

## 安装后直接调用

需要 Node.js 22.20+：

```bash
npx skills add edward-skills/skill-verifier --skill skill-verifier
```

在安装器里选择你的 agent，也可以用 `--agent codex` 等参数明确指定。完整安装包是 [`skill-verifier/`](skill-verifier/)，手工安装时应复制整个目录。

然后发给 agent：

```text
用 skill-verifier 检查 /目标skill的绝对路径。
先做离线验证：阅读脚本和实际契约，选择正常、边界和已知错误用例，
交付原始证据、具体修正建议和未验证范围。
不要调用在线模型或外部账号，也不要修改目标 skill。
```

安装器不会自动安装 Python 依赖、模型 CLI 或导入已有认证。

## 不需要账号的快测

需要 Python 3.9+，核心不需要额外库：

```bash
git clone https://github.com/edward-skills/skill-verifier.git
cd skill-verifier
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-clean
```

查看打印出的 `evidence/report.md`。还可以验证已知缺陷和依赖阻塞：

```bash
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-defect --scenario defect
python3 skill-verifier/scripts/demo.py --out /tmp/skill-verifier-blocked --scenario blocked
```

每次必须用新目录。正常脚本把整数翻倍；故障脚本改为平方；阻塞例故意没有解释器。可用的强制隔离环境下，正常例应通过，故障例应失败，阻塞例应 incomplete。`--isolation none` 只做诊断，断言通过也不会得到完整门槛通过。请求的沙箱不可用时保持阻塞，不自动降级。

## 检查自己的 skill

```bash
python3 skill-verifier/scripts/verifier.py offline-init --skill /目标skill目录 --profile auto --out /tmp/target-plan
```

生成库存、语法结果和禁用的用例草案。审阅实际 CLI、依赖、契约责任和运行文件清单，补入独立断言后再启用。代码、数据、媒体、文档、自动化模板提供起点，不能替代测试设计。然后运行：

```bash
python3 skill-verifier/scripts/verifier.py offline-validate /tmp/target-plan/suite.json
python3 skill-verifier/scripts/verifier.py offline-run --skill /目标skill目录 --suite /tmp/target-plan/suite.json --config /tmp/target-plan/config.json --runtime-manifest /tmp/target-plan/runtime-proposal.json --out /tmp/target-evidence
```

`runtime-proposal.json` 必须先审阅并移除答案/评分资料；默认只复制 SKILL.md。结果目录保留步骤、退出码、stdout/stderr、产物、哈希、每次重复，以及 findings/coverage/report。完整协议见[离线 QA](skill-verifier/references/offline.md)。

JSON/YAML/CSV、精确文本、哈希和图片属性可以确定性检查；语义、视觉可读性等使用 manual rubric，未导入绑定原始产物哈希的评审前保持 pending。根因假设与修复验证分别标记，不自动把建议写成已证实结论。

## 依赖与验证边界

兼容性按实际工具能力判断，不按厂商白名单限定。随包的 Codex、Claude Code、Gemini CLI adapter 示例，与 Cursor/OpenCode 安装证据、Aident/WorkBuddy 同步检查是不同层次。Hermes、pi、SpaceX Grok Bot、Meta Muse 已有文档适配说明，其安装、原生触发和真实任务仍未验收。见[宿主适配](skill-verifier/references/harnesses.md)与[待填写的能力模板](skill-verifier/examples/harness-review.json)。

- 核心只需 Python 3.9+；完整 YAML 用可选 PyYAML，像素检查用可选 Pillow。
- 本地强制隔离已独立验证的是 macOS；Linux bubblewrap 实机和 Windows 强制隔离未通过本次验收。
- 候选/基线模型调用需要自行配置 agent、模型和窄权限认证；本包不默认启用。
- script/artifact 的 required 契约才影响离线硬性门槛；agent 规则和建议保留观察，不强加成 helper 缺陷。
- 文件存在、退出 0 或手填 verified 都不能代替任务质量和隔离证据。

0.3.2 已通过 macOS 离线独立 QA：五个安装目标的 42 文件一致，安装副本中的 94 项作者测试零跳过，另有 25 项独立探针通过。作者也另外复测了 GitHub 全新安装和安装后离线执行。安装检查不代表原生发现或模型效果验证。[0.3.2 QA 记录](docs/qa/v0.3.2.md) · [兼容性与证据](docs/validation.md) · [发行说明](docs/releases/v0.3.2.md)。

硬链接检查不识别所有独立答案副本，运行资料仍需内容审阅；不承诺对特权并发篡改无竞态。在线模型、原生发现、跨 harness、Linux 强制隔离和外部账号操作继续待验证。

开发回归可在虚拟环境安装 `requirements-test.txt`，运行 `python scripts/validate_repository.py` 与 `python -m unittest discover -s skill-verifier/tests -v`。不会为了验证而修改全局 agent 配置。
