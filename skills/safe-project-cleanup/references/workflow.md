# 脚本协议与判断规则

Windows side。Python 3.11+，标准库；只使用已安装 Git，不安装依赖。运行 `py -3.11 -B -X utf8 <skill>\scripts\cleanup.py --help`。所有操作命令在子命令前指定 `--workspace-root <独立绝对目录>`；下文省略此公共参数，`--out` 必须在该工作目录内，工作目录不可被清理。JSON 中的命令只是描述，脚本不执行它们。

## 计划与批准

先检查当前工程 AGENTS.md。清单指定绝对白名单、保护路径、单次字节预算，每个条目指定 `path`、`action`（`delete`/`archive`/`archive-delete`）、`purpose`（`derived`/`old-version`）、`resource_class`（A/B/C）、判断依据 `basis` 和最近的活动检查 `inactive_evidence`。

派生物还必须有具体 `rebuild` 方法。B 类须先核对依赖锁文件、准确版本、供应源及本地修改，尽量走官方限域入口。脚本 B 类条目必须有 `dependencies`：`manifests` 为现存清单绝对路径列表，`versions`/`download` 为实际版本与获取核对证据，`reference_scope` 为实际覆盖范围，`local_modifications` 必须为 `none_verified`，`offline_unique` 必须为 false。这些字段是已完成审核的记录，脚本不替代下载/引用/本地修改调查，也不能凭自行填值声称通过。本脚本不运行官方清理命令，避免命令越权；无法限域时只报告。保护文件默认阻断整个目录。确有逐文件可重建证据时才填写精确相对路径 `rebuildable_files`；秘密、Git 元数据不能借此覆盖。原始日志、唯一发布等未经保留不能覆盖。`exclusions` 非空会被拒绝，请改为多个精确叶子候选。

`plan --spec spec.json --out plan.json` 写入文件身份、属性、大小、时间、SHA-256 及 Git 基线；它不产生授权。大目标超过默认 20 秒/10000 条目/4 GiB 完整快照上限会被拒绝；拆分候选或在 spec 中明确增大 `max_bytes`，保持有界。秘密文件不读取内容，也不被归档。

用户审核清单后，由 Codex 根据真实用户消息创建独立批准记录（模拟测试使用本轮已批准的测试范围）。不得自行发明授权：

```json
{
  "plan_id": "复制实际计划 ID",
  "plan_sha256": "cleanup.digest(实际计划 JSON) 的值",
  "authorization_source": "真实用户消息的日期、标识和批准范围，勿含秘密",
  "items": [
    {
      "path": "D:\\已确认工程\\build\\objects",
      "action": "delete",
      "permanent_delete": true,
      "retire_entire_version": false,
      "inactive_evidence": "执行前新核对的任务/进程/占用证据"
    }
  ]
}
```

取得规范 JSON 摘要可用 `py -3.11 -B -X utf8 -c "import sys; sys.path.insert(0, r'<skill>\scripts'); import cleanup; print(cleanup.digest(cleanup.load(r'<plan.json>')))"`。不把计划本身改成 approved。

`execute --plan plan.json --out preview.json` 默认 dry-run；`--apply --approval approval.json` 只处理批准的子集。也可 `--apply --policy policy.json` 使用已由用户明确批准的持久工程策略；两者互斥。策略限制根目录、资源类型、用途、动作、保护项、闲置规则、预算及撤销方法；永久删除和整工程淘汰必须显式包含。策略只是授权记录载体，脚本无法鉴别人类来源，Codex 必须先核对真实授权及本轮新活动证据。PAUSED/REVOKED 策略不可执行。禁止把缓存授权解释成版本淘汰授权。

## 版本证据

`versions --manifest version-set.json --out versions.json` 按 v1/v2/v3/v4/v10 数字排序。身份对象包含工程、主线和硬件；不同身份的目录保留。每个版本显式给出 current、稳定性证据、active/frozen/keep。没有稳定回退或精简授权则全部保留。

默认保留 current 和另一已验证稳定版本；精简模式额外要求 `single_version_authorized: true` 和真实会话批准，当前版本必须就是最新稳定版本。数量不能解除其他保护。

每个淘汰候选需要 `inactive_evidence` 和 `independent_retained_evidence`。引用搜索范围用 `reference_roots`；`reference_scope_confirmed` 表示已由 Codex/用户确认此范围覆盖已知依赖，同时报告未覆盖的机器/二进制/其他工程。搜索只读文档/源码/配置（不读 .env/签名文件），默认 15 秒/5000 条目/每文件 1 MiB；只记录匹配位置，不记录原文。发现引用、跳过或截断就阻断。目录名称子串命中偏保守，手工核查后更新证据范围，不能以局部搜索零命中宣称全机无依赖。

对所有普通文件逐项比较保留版本同相对路径 SHA-256，或 `preserved_files` 指向的独立保留文件。秘密文件始终阻断，不复制到报告。独有数据、失败日志、固件、媒体、配置等先提出最小保留方案，授权复制并核对后再淘汰。明确已淘汰的源码/配置差异可用 `obsolete_implementation_authorized`，但不涵盖原始材料。重要配置归入 `preserved_files`，不要随旧实现销毁。

Git 需只读核对状态、完整引用及所有 reachable/reflog 提交是否在保留仓库中；包括 detached HEAD。额外 `local_history_reviewed` 记录对 dangling 对象、stash、其他有价值本地历史的人工核对。Git 比较不完整、未提交工作、独有历史、嵌套仓库、子模块、共享 Git metadata/worktree 都阻断。原始状态检查包括未跟踪数量，不因 untracked/ignored 本身许可或永久禁止；逐项材料检查仍适用。

整版本删除只允许 `purpose: old-version` 且版本报告为 RETIRE_CANDIDATE。保留目录和资料保留位置加入保护路径，拒绝删除它们的父目录。模型、SDK、工具链等 C 类先列建议；它们不是 old-version 就不能假借版本策略直接删除。

## 路径、占用与竞态边界

只支持绝对本地 Windows 卷路径。拒绝 UNC、设备路径、盘根、用户根、`..`、通配符、ADS 路径、保留设备名、尾随点/空格、短名别名、任何重解析点。包含关系按路径组件判断。脚本完全不执行清单中的代码。

扫描可统计硬链接/压缩/稀疏的逻辑大小，不能将它们折算成真实释放量。为避免错误保留/归档，本实现的变更操作拒绝硬链接、压缩/稀疏/加密/offline 文件及 NTFS 额外数据流。拒绝整个 Codex 管理目录直接变更，使用当前实际公开的 worktree 归档能力；先核对归属、固定、活跃及 ignored 独有内容，能力缺失只报告。镜像、保留来源和共享管理目录按适用工程规则保护。

执行先重新做完整快照与 Git/版本核对，再用 Win32 handle 固定祖先和选中目录（禁止共享删除）、独占选中文件、按 handle 校验文件 ID/内容并按 handle 删除。目标被换成链接、文件被替换/改写、已被其他进程占用均拒绝。Windows 命名 mutex 阻断同一 Windows 会话内本脚本的并发清理，不在白名单外创建/删除控制文件。它不协调其他登录会话或其他清理工具；放弃/占用状态直接拒绝，不强停、不自动重试。

`ponytail:` 不能从文件锁证明整个工程闲置，也不能阻止其他程序在已固定目录中新建子项。因此须人工核对任务、构建、服务和可见使用状态；未知不执行。执行只删除快照中固定的对象，新子项不会被递归删除，父目录非空时报告部分失败。它不保证对抗拥有写权限的恶意用户/内核、卷离线或所有并发竞态；升级路径是经审核的服务停机窗口或文件系统事务/可信原生管理工具。不要称为消除了所有竞态。

删除失败按条目保留已完成字节和未完成状态。永久删除不可撤销。只有计划和批准记录不构成备份。

## 归档、恢复与收益

`archive` 生成 ZIP/逐文件哈希清单并回读校验，保留原件；要求目标空间至少逻辑大小加 1 MiB。下一步用 `restore` 排练恢复到**不存在**的新目录，再执行经重新核对的删除计划。`archive-delete` 仅在已有对应内容的恢复排练证据时使用。压缩/复制/校验/空间不足则原件保留；不自动删除失败 ZIP 或恢复 staging。

`verify-archive` 校验清单、路径、大小、CRC/内容哈希、额外条目与重复名称，不代表恢复排练通过。`restore` 默认 dry-run，`--apply` 在白名单下的新目录恢复，不覆盖已存在路径；拒绝恶意 ZIP 路径/链接。恢复验证内容哈希，不恢复 ACL、ADS、所有时间戳或单文件归档（后者只可校验）。备份源在检查和读取期间独占，私有 staging 的目录被固定；失败 staging 保留供核查。

分别保留候选逻辑大小、处理/删除逻辑大小、归档实占字节、涉及卷的两次实测 free。ZIP 在同盘会占空间；归档不删除源不会释放源空间。本实现不提供回收站/隔离移动，不把它们算成释放量。C 搬到 D 不增加总容量。其他程序和卷写入会影响实测差值，不将差值完全归因本操作。

重建命令由 Codex 审核后在另行授权范围内执行；脚本不执行不可信仓库命令。核对保护文件/Git 状态并保留既有失败，不自动认定工程完整性、硬件或用户验收通过。
