# 发布与转发文案

以下是可直接转发的文案；仅使用已发布功能，不宣称真实工程自动验收或固定节省量。

## 中文短介绍

我发布了一个 Windows Codex skill：**safe-project-cleanup · 工程空间管家**。
工程越做越大，它先有界盘点占用，再核对构建缓存、依赖和旧版本；按用户批准的精确清单执行，并报告实际结果。
默认只读，保留源码、日志、冻结资料和 Git 历史，支持归档校验与恢复排练。
Python 标准库实现，MIT 开源，安装和示例都在仓库：
https://github.com/eastpeak001/safe-project-cleanup

## 中文长介绍

做固件、Android 或 Python 工程时，最占地方的往往不只是一个 build：依赖、旧验证目录、发布包和多个版本会一起堆积。

**工程空间管家**把清理变成可审核的过程：先确认范围并分批盘点，再核对每个候选的来源、可重建依据、保护资料和引用；生成精确清单和预演后，由用户批准具体动作。执行前再次检查文件身份，执行后区分逻辑删除量、归档占用和卷的实测空间变化。

旧版本默认保留当前工程和一个已验证回退版本，也支持用户明确选择仅保留最新稳定版。归档先校验内容，恢复必须到新目录；需要先归档再删除时，还要有实际恢复排练证据。

首版提供中文 skill、中英文介绍、安装提示词、策略模板和 Windows 模拟测试。它不会替代项目自身的验收，也不承诺消除所有竞态。欢迎用脱敏模拟工程复现问题或提交改进。

仓库：https://github.com/eastpeak001/safe-project-cleanup
安装包：https://github.com/eastpeak001/safe-project-cleanup/releases/tag/v0.1.0

## English announcement

Released **safe-project-cleanup**, a Windows-first Codex skill for growing development projects.
Inspect storage with explicit bounds, review caches and old versions with evidence, then apply
only the exact authorized items. Dry-run by default, protected source/history, content-verified
archives and separate restore rehearsal. Python standard-library runtime, MIT licensed.

Instructions are in Chinese, with an English introduction and pinned-version installation guide.
Tests use isolated simulated projects; real-project acceptance remains project-specific.

https://github.com/eastpeak001/safe-project-cleanup
