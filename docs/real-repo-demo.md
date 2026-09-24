# 完整仓库修复演示：精确编辑的回归

此案例在本项目的**完整仓库副本**上运行，而非只给 Agent 两个小文件。为了可重复，先用补丁人为注入一处回归：`replace_text_once()` 错把“文本出现两次”视为可编辑，破坏“只允许唯一匹配”的安全约束。项目已有的测试会失败。它是**合成回归**，不是外部开源项目的真实 issue；模型修复成功率尚需真实运行记录，不能预先宣称。

以下命令从项目根目录执行。只对信任此仓库及其测试代码的环境运行；模型测试和最终复验都会执行仓库 Python 代码。演示使用临时副本，不触碰当前工作区及未提交改动。不要把密钥写入命令或报告。

```bash
project_root=$PWD
demo_root=$(mktemp -d /tmp/coding-agent-real-repo.XXXXXX)
git clone --quiet . "$demo_root/repo"
cd "$demo_root/repo"
git apply docs/demo-regression.patch
"$project_root/.venv/bin/python" -m pytest -q test_main.py::test_edit_file_rejects_multiple_matches_without_changing_file
```

此时预期测试非零退出。记录输出后，回到原仓库，用其安装好的入口运行 Agent（`demo_root` 是上一段终端里的变量）：

```bash
cd "$project_root"
.venv/bin/coding-agent \
  --workspace "$demo_root/repo" \
  --allow-edit \
  --rollback-on-failure \
  --max-steps 12 \
  --report-json "$demo_root/repair.json" \
  "修复精确编辑在同一文本出现两次时未拒绝修改的回归。先定位现有测试与实现，不要修改测试文件；修复后运行测试。"
```

完成后检查报告和实际差异：

```bash
git -C "$demo_root/repo" status --short
git -C "$demo_root/repo" diff -- file_tools.py test_main.py
.venv/bin/coding-agent-evaluate "$demo_root/repair.json"
.venv/bin/python docs/verify_real_repo_demo.py \
  --report "$demo_root/repair.json" --workspace "$demo_root/repo"
```

验收器要求：报告为成功、CLI 独立复验通过、报告中的任务前后变化仅为
`file_tools.py`，演示副本没有其他已跟踪或未跟踪文件变化，并由验收器再次
运行完整 pytest。它不请求模型，但会执行副本中的测试代码，因此只用于受信仓库。
注入回归是相对 Git `HEAD` 的未提交修改；若 Agent 恰好恢复为 `HEAD` 的原实现，
最后的 `git diff` 会是**空的**，这并不表示 Agent 没有编辑。实际编辑归因应看
`repair.json` 的 `workspace_changes`（相对任务开始时），并结合复验结果。
若 Agent 进程非零退出或验收器未通过，保留 `repair.json` 及失败轨迹；开启的
回滚会尝试恢复任务开始时的 Git 可见普通文件状态，注入的回归属于任务开始
状态，会被保留。不能仅凭模型最终文字或定向测试通过判成功。

该仓库副本和报告都在 `demo_root` 下，演示结束前可保留审查。若需要清理，应在确认路径后由操作者手动删除；本指引不自动清理。
