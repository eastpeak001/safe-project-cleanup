# Windows side：安装与第一次盘点

## 安装指定版本

推荐在 Codex 中直接发送：

```text
使用 $skill-installer 安装：
https://github.com/eastpeak001/safe-project-cleanup/tree/v0.1.0/skills/safe-project-cleanup
```

需要调用内置安装脚本时，先确认它的实际路径，然后使用：

```powershell
py -3.11 -B -X utf8 '<实际 skill-installer 目录>\scripts\install-skill-from-github.py' --repo eastpeak001/safe-project-cleanup --ref v0.1.0 --path skills/safe-project-cleanup
```

安装器发现目标已经存在会停止，不会自动覆盖。更新前先保留个人修改，并避免在 `.agents/skills` 和 `.codex/skills` 同时安装同名副本。

手动安装：从 Release 下载 ZIP 和 `SHA256SUMS.txt`，用 `Get-FileHash -Algorithm SHA256` 核对 ZIP；再把 ZIP 内的 `safe-project-cleanup` 目录解压到 `$env:USERPROFILE\.agents\skills`。首次解压目标必须是新目录。用户级技能目录和发现行为参考 [OpenAI 官方文档](https://learn.chatgpt.com/docs/build-skills)。

## 用一个模拟工程试用

在 Codex 中发送下面提示词，不需要输入一大段脚本：

```text
Windows side，使用 $safe-project-cleanup。
在我确认的非系统盘工作位置创建一个全新的模拟工程和独立报告目录。
模拟工程包含 src/main.py、evidence/history.log 和 build/part.o。
只对这个模拟目录盘点和生成计划；保护源码与历史日志。
预演后展示 part.o 的精确路径、大小、依据和恢复方式。
先停在清单审核处，不操作任何真实工程。
```

执行模拟删除仍须你明确批准具体清单。不要把“试用 skill”理解为可以清理其他工程。

## 工具参数

```powershell
# 路径仅为示例；替换为实际安装、工程和工作目录。
$script = Join-Path $env:USERPROFILE '.agents\skills\safe-project-cleanup\scripts\cleanup.py'
$workspace = 'D:\cleanup-reports'
py -3.11 -B -X utf8 $script --help
py -3.11 -B -X utf8 $script --workspace-root $workspace scan --root 'D:\projects\demo' --out "$workspace\run-001\inventory.json" --max-seconds 40 --max-entries 60000 --max-depth 10
```

可用子命令：`scan`、`plan`、`versions`、`execute`、`verify-archive`、`restore`。
`--workspace-root` 是所有命令的公共必填参数，位于子命令之前。工作目录可以使用任何受支持的本地卷，应与待清理目标分开；不得使用盘根、用户根或 skill 安装目录。
`--out` 必须是工作目录内不存在的新文件。工作目录受保护，不能被当作缓存删除。
首次盘点不需要批准文件。`execute` 和 `restore` 默认预演；实际变更需另行核对真实授权。

计划 JSON、批准记录、依赖证据、版本策略和恢复格式见 [协议](../skills/safe-project-cleanup/references/workflow.md)，常用提示词见 [examples.md](../skills/safe-project-cleanup/references/examples.md)。JSON 中描述的重建命令不会被脚本自动执行。

## 读懂结果

候选大小表示待审查文件的逻辑字节；实际删除字节来自执行报告。归档占用另算。
可用空间变化受其他程序影响，不能全部归因于本次操作。扫描截断时继续指定子目录，不能把局部盘点称为全盘审计。

遇到锁、目标变化、保护资料或未知使用状态，保留文件并报告原因，不强停进程、不放宽批准范围。
