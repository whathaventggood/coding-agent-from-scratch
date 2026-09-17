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

        before = run_tests(".", str(workspace))
        print("修复前测试：", before)
        if not before.is_error:
            raise SystemExit("示例错误未触发测试失败")

        answer = read_file_and_answer(
            "这是一个受信的临时工作区，里面有一个未通过的测试。"
            "先调用 run_tests，path 填 '.'，根据失败信息定位问题；"
            "按需使用文件工具检查并修复代码，再调用 run_tests 复测。"
            "只有复测通过才能报告修复成功。",
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
