import os
from pathlib import Path

from deepseek_model import read_file_and_answer


if __name__ == "__main__":
    workspace_root = Path(__file__).resolve().parent
    os.chdir(workspace_root)

    answer = read_file_and_answer(
        "请调用 run_tests 工具，path 参数填写 '.'，"
        "运行当前工作区的测试，并根据工具结果报告通过或失败。"
        "如果没有调用工具，不要声称测试通过。",
        workspace_root=str(workspace_root),
    )

    print("模型回答：", answer)