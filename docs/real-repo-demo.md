# 完整仓库修复演示：精确编辑的回归

此案例在本项目的**完整仓库副本**上运行，而非只给 Agent 两个小文件。为了可重复，先用补丁人为注入一处回归：`replace_text_once()` 错把“文本出现两次”视为可编辑，破坏“只允许唯一匹配”的安全约束。项目已有的测试会失败。它是**合成回归**，不是外部开源项目的真实 issue；模型修复成功率尚需真实运行记录，不能预先宣称。

以下命令从项目根目录执行。只对信任此仓库及其测试代码的环境运行；模型测试和最终复验都会执行仓库 Python 代码。演示使用临时副本，不触碰当前工作区及未提交改动。不要把密钥写入命令或报告。

```bash
demo_root=$(mktemp -d /tmp/coding-agent-real-repo.XXXXXX)
git clone --quiet . "$demo_root/repo"
cd "$demo_root/repo"
git apply docs/demo-regression.patch
"$OLDPWD/.venv/bin/python" -m pytest -q test_main.py::test_edit_file_rejects_multiple_matches_without_changing_file
```

此时预期测试非零退出。记录输出后，回到原仓库，用其安装好的入口运行 Agent（`demo_root` 是上一段终端里的变量）：

```bash
cd "$OLDPWD"
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
```

验收需同时满足：Agent 返回完成、CLI 全量独立复验通过、退出码为 0，且 Git 差异只包含符合任务目标的源码修复、不修改测试。若失败，保留 `repair.json` 记录失败原因及轨迹；开启的回滚会尝试恢复任务开始时的 Git 可见普通文件状态，注入的回归本身属于任务开始状态，会被保留。不能仅凭模型最终文字或定向测试通过判成功。

该仓库副本和报告都在 `demo_root` 下，演示结束前可保留审查。若需要清理，应在确认路径后由操作者手动删除；本指引不自动清理。
