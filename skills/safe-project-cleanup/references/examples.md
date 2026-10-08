# 调用与工程模板

Windows side。在工程聊天中直接发送：

```text
使用 $safe-project-cleanup，只读盘点当前已确认工程，限 40 秒和 60000 条目。先列主要空间占用、覆盖和未知，再生成待审核清单。先确认工程外的独立报告目录，优先非系统盘。本轮不删除、归档或重建真实资源。
```

```text
使用 $safe-project-cleanup，执行我刚明确批准的计划 <绝对路径> 中的 <精确条目路径/动作>。复核目标快照、保护项、当前活动及批准类型；变化就跳过。生成独立执行报告，核对保护文件和 Git，再运行已审核的最小软件验证。禁止扩展到其他版本或共享资源。
```

```text
使用 $safe-project-cleanup，核对 <ZIP绝对路径>，并在我指定的 <允许根目录> 下恢复到新目录 <不存在的路径>。不覆盖已有文件。报告哈希核对、恢复能力和额外空间占用。
```

默认版本策略示例：

```text
使用 $safe-project-cleanup 审查 <工程版本集合根目录>，采用 current-and-rollback。v4 是当前工程，v3 有 <稳定性报告>；先保留它们以及所有活跃/冻结/共享依赖版本。只将同一工程、主线和硬件的 v1/v2 列入待淘汰清单，检查独有资料、Git历史、保留版本与已知其他工程引用。本轮只出计划。
```

精简策略示例：

```text
使用 $safe-project-cleanup 审查 <工程版本集合根目录>，我明确选择 latest-stable-only。v4 的稳定性证据为 <报告>，所需资料及独立运行证据为 <报告>。v1/v2/v3 先列候选，冻结/活跃/独有材料/未知引用继续保留。选择精简策略不代替具体永久删除批准。
```

可选工程 AGENTS.md 收尾约定（先建议；未经要求不改现有工程）：

```markdown
## 工程空间收尾
收尾时可使用 safe-project-cleanup 做有界只读盘点，报告写到工程外的新目录。
当前工程根和保护路径：<实际确认路径>。
旧版本默认保留当前版本和一个不同的、已验证回退版本；活跃、冻结、共享依赖另保留。
只按真实用户批准清单或已批准工程策略执行。未授权时只提出建议。
来源/活动/引用/资料保留不明时跳过；保留源码、数据、日志、失败证据、发布、签名和 Git 历史。
最小验证：<此工程已审核的命令及已知基线失败>。
```

可复制的脚本调用（实际替换工程和新报告路径）：

```powershell
# Windows side；输出目录需提前确认位于被盘点工程之外。
$cleanupScript = Join-Path $env:USERPROFILE '.agents\skills\safe-project-cleanup\scripts\cleanup.py'
# 使用 skill-installer 时也可能位于 .codex\skills；以实际安装路径为准。
$cleanupWorkspace = 'D:\cleanup-reports' # 示例：替换为本机已确认的独立目录
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace scan --root 'D:\已确认工程' --out 'D:\cleanup-reports\新报告目录\inventory.json' --max-seconds 40 --max-entries 60000
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace plan --spec 'D:\cleanup-reports\spec.json' --out 'D:\cleanup-reports\plan.json'
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace execute --plan 'D:\cleanup-reports\plan.json' --out 'D:\cleanup-reports\dry-run.json'
# 下面命令仅在用户已明确批准后使用。
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace execute --plan 'D:\cleanup-reports\plan.json' --approval 'D:\cleanup-reports\approval.json' --apply --out 'D:\cleanup-reports\execution.json'
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace verify-archive --archive 'D:\cleanup-reports\实际归档.zip' --out 'D:\cleanup-reports\archive-check.json'
py -3.11 -B -X utf8 $cleanupScript --workspace-root $cleanupWorkspace restore --archive 'D:\cleanup-reports\实际归档.zip' --root 'D:\已确认恢复根' --dest 'D:\已确认恢复根\新恢复副本' --out 'D:\cleanup-reports\restore-preview.json'
```

项目策略用 [policy-template.json](policy-template.json)，版本集合用 [version-template.json](version-template.json)。模板保持未批准/暂停状态，替换身份、路径及证据后审核；不要直接运行占位符。撤销策略可改成 REVOKED，或移走该策略文件。不要创建定时任务作为使用本技能的前提。
