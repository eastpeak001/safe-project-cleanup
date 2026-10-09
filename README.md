# codex项目残留清理 · 工程空间管家

**让 Codex 清理工程空间：先看清占用，再按批准清单执行。**

[English](README.en.md) · [安装与示例](docs/getting-started.md) · [发布记录](CHANGELOG.md) · [宣传文案](docs/promotion.md)

[![Windows tests](https://github.com/eastpeak001/safe-project-cleanup/actions/workflows/windows-tests.yml/badge.svg)](https://github.com/eastpeak001/safe-project-cleanup/actions/workflows/windows-tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

给 Windows 开发者的 Codex skill。工程越做越大时，先找到构建产物、缓存和旧版本的主要占用，再由 Codex 核对可重建依据、保留资料和实际授权。清理后分别报告删除的逻辑大小与磁盘实测变化。

适合固件、Android、Python、桌面应用等工程的空间整理。它包含中文工作流、标准库 Python 工具、旧版本策略模板和模拟行为测试，不依赖 EverMe 或其他记忆插件。

```mermaid
flowchart LR
    A[确认工程和报告目录] --> B[有界只读盘点]
    B --> C[核对来源、保护项与旧版本]
    C --> D[精确清单与预演]
    D --> E[用户批准清单或工程策略]
    E --> F[重新校验身份后执行]
    F --> G[保护项、恢复能力与空间核验]
```

## 能帮你做什么

| 场景 | 处理方式 |
| --- | --- |
| 大工程不知道哪里占空间 | 限制时间、条目和深度，报告覆盖、截断和下一批扫描位置 |
| build、依赖缓存越来越大 | 目录名仅作线索，核对生成规则、锁文件、版本和本地修改 |
| v1/v2/v3/v10 堆积 | 数字排序；默认保留当前版本和一个已验证回退版本 |
| 旧版本仍被其他工程引用 | 搜索已确认范围，记录未知与未覆盖范围，保留有引用的版本 |
| 希望先归档再处理 | ZIP 内容校验、恢复到新目录排练，之后另按批准处理原件 |
| 需要知道到底省了多少 | 区分候选大小、实际删除、归档占用和涉及卷的可用空间变化 |

## 安装

在 Codex 中发送：

```text
使用 $skill-installer 安装这个指定版本的 skill：
https://github.com/eastpeak001/safe-project-cleanup/tree/v0.1.0/skills/safe-project-cleanup
```

也可下载 [Release 安装包](https://github.com/eastpeak001/safe-project-cleanup/releases/tag/v0.1.0)，校验 SHA256 后，把其中的 `safe-project-cleanup` 文件夹放入用户级 `.agents/skills`。已安装同名 skill 时，先检查现有版本，避免并存或覆盖个人修改。详细步骤见 [安装指南](docs/getting-started.md)。Codex 通常会自动发现变更；若未出现，重启 Codex。

要求：**Windows、本地卷、Python 3.11+**。运行时仅使用 Python 标准库；Git 工程调查还需要已安装 Git。

## 第一次使用

```text
使用 $safe-project-cleanup，只读盘点当前已确认工程。
先确认工程外的独立报告目录，优先非系统盘。
限制 40 秒、60000 条目、深度 10；报告主要占用、保护项、覆盖和未知。
只生成待审核清单，本轮不删除、不归档、不重建。
```

所有工具命令都显式指定报告工作目录：

```powershell
# Windows side；替换为本机的实际路径，不要求存在 D 盘。
$script = Join-Path $env:USERPROFILE '.agents\skills\safe-project-cleanup\scripts\cleanup.py'
$workspace = 'D:\cleanup-reports'
py -3.11 -B -X utf8 $script --workspace-root $workspace scan --root 'D:\projects\demo' --out "$workspace\run-001\inventory.json" --max-seconds 40 --max-entries 60000 --max-depth 10
```

skill-installer 的安装位置可能是 `.codex/skills`；命令中的 `$script` 应指向实际安装位置。

## 清理边界

- **默认只读。** `--apply`、计划里的标记和模型自己填写的批准记录，都不能替代真实用户授权；Codex 必须核对实际消息或已批准工程策略。
- 默认保护源码、配置、锁文件、秘密与签名、PCB、数据、日志、冻结发布和 Git 历史。保护内容在 build 或 ignored 内仍受保护。
- 拒绝路径逃逸、重解析点、目标替换、锁定文件和嵌套候选；变更操作不支持硬链接、压缩、稀疏、加密、offline 文件或 NTFS 额外数据流。
- 同一 Windows 会话的脚本并发受 mutex 控制；仍需核对构建、服务和使用状态。新出现的文件不会被递归删除。不能保证消除所有竞态。
- 永久删除不可撤销。ZIP 校验与实际恢复排练是两项检查；恢复不保留 ACL、ADS 或全部时间戳。脚本不自动执行重建、下载或硬件验收。

详细协议见 [workflow.md](skills/safe-project-cleanup/references/workflow.md)。

## 验证与参与

Windows CI 运行 34 项原有行为测试及安装包/CLI 集成测试，覆盖未提交资料、保护文件、路径与链接、锁、批准、版本引用、归档和恢复。测试只使用新建模拟目录；它们不等同于你真实工程的验收。

发现问题请提交 [Issue](https://github.com/eastpeak001/safe-project-cleanup/issues)，提供脱敏后的复现步骤和环境信息。贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。本项目由 PingGu（eastpeak001）发布，采用 [MIT](LICENSE) 许可证。
