## 工程空间管家 v0.1.0

让 Codex 清理工程空间：先看清占用，再按批准清单执行。

- Windows 本地卷有界盘点，报告覆盖、截断与下一批扫描位置。
- 精确计划、真实授权核对与默认预演；执行前重查文件身份与保护项。
- 旧版本默认保留当前版本和一个已验证回退版本。
- ZIP 内容校验、恢复到新目录排练，以及分别报告删除量和空间变化。
- 显式工作目录，Python 3.11+ 标准库实现，无强制记忆插件依赖。

### 安装

```text
使用 $skill-installer 安装：
https://github.com/eastpeak001/safe-project-cleanup/tree/v0.1.0/skills/safe-project-cleanup
```

附件 ZIP 包含可安装 skill 和 MIT 许可证；下载后用 `SHA256SUMS.txt` 校验。
已有同名安装时，先检查个人修改。首次使用从只读盘点开始。

### 验证与限制

发布版本通过 Windows 行为测试和安装包/CLI 集成测试；具体远端结果见仓库 Actions。
测试仅针对新建模拟目录，不代表任何真实工程、硬件或用户验收通过。
不支持 UNC 与特殊文件变更，不恢复 ACL/ADS，不保证消除所有竞态。永久删除不可撤销。

## English

First public release of a Windows-first Codex skill for bounded project inventory,
exact authorization, cache/old-version review, and verified archive/restore workflows.
Python 3.11+ standard-library runtime. Every operation has an explicit report workspace.
Chinese skill instructions with an English introduction. MIT licensed.

Start with read-only inventory. Tests cover isolated fixtures; live project acceptance is
separate. Verify the release ZIP using the attached SHA256 checksum before manual installation.
