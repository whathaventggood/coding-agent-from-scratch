from pathlib import Path
from tempfile import TemporaryDirectory

from command_tool import run_tests
from deepseek_model import read_file_and_answer


def main():
    with TemporaryDirectory(prefix="agent-demo-") as temp_dir:
        workspace = Path(temp_dir)

        (workspace / "calculator.py").write_text(
            "def add(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        (workspace / "test_calculator.py").write_text(
            "from calculator import add\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )

        answer = read_file_and_answer(
            "工作区的 calculator.py 有一个加法错误。"
            "先调用 search_file，在 calculator.py 中搜索 'return a - b'；"
            "然后调用 edit_file，只把 'return a - b' 改为 'return a + b'；"
            "最后调用 run_tests，path 填 '.'。"
            "请根据工具结果报告修复是否成功。",
            workspace_root=str(workspace),
            allow_edit=True,
            max_steps=8,
        )

        print("模型回答：", answer)
        print("最终代码：")
        print((workspace / "calculator.py").read_text(encoding="utf-8"))

        check = run_tests(".", str(workspace))
        print("本地独立复验：", check)

        if check.is_error:
            raise SystemExit("演示未通过")


if __name__ == "__main__":
    main()
