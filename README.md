# 从零实现 Coding Agent

这是一个用于学习 Python 工程与 Agent 原理的 Coding Agent 项目。

## 当前功能

- 解析 JSON 工具请求
- 读取文本文件
- 列出目录中的文件
- 根据名称分发工具
- 返回结构化错误信息
- 在单个文本文件中搜索关键词并返回匹配行号
- 将无效 UTF-8 文件转换为清晰的错误结果
- 精确替换文件中的唯一文本，零匹配或多匹配时拒绝写入
- 支持用空字符串删除指定文本
- 使用模拟模型响应演练工具调用与最终回答循环，并限制最大执行步数
- 接入 DeepSeek，实现真实的 read_file 工具调用、结果回传和最大步数限制
- 将模型生成的无效 JSON 参数转换为工具错误并回传

## 安装依赖

```bash
python -m pip install -r requirements-dev.txt
```

## 配置 DeepSeek

运行前设置环境变量：

```bash
export DEEPSEEK_API_KEY="你的密钥"
```

不要把真实 API Key 写入代码或提交到 Git。

## 运行 DeepSeek 读取示例

```bash
python deepseek_model.py
```

当前真实模型循环只开放 `read_file` 工具。
