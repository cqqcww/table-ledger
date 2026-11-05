# 安装说明

## 1. 准备基础运行环境

需要一个**独立取得、许可允许使用**的兼容后端。本仓库不重新分发或重新许可它，也不自动下载外部代码。

将后端根目录设为 `TABLELEDGER_BACKEND_ROOT`，包名默认为 `tableqa`，可由 `TABLELEDGER_BACKEND_PACKAGE` 覆盖。后端应提供以下接口：

| 模块 | 必需接口 |
|---|---|
| schema | AnswerError、compact_json、json_loads、normalize_response、validate_structure |
| cloud | StopRun |
| pipeline | atomic_json |
| documents | image_content；输入文档具有sha256与images属性 |
| prompts | COMMON |
| xlsxio | Question，含id、file_name、question_type、question、table_hint、answer_format |

后端同时应安装自身的图像处理依赖。原工作区中经过验证的后端满足这些约定；未经适配的其他版本不保证兼容，先运行诊断命令。模型服务不由本发布包配置。

## 2. 安装扩展

```bash
python -m pip install .
export TABLELEDGER_BACKEND_ROOT=/absolute/path/to/backend
python -m tableledger check
```

`.env.example`仅是变量清单，不自动读取。所有真实凭据由后端或调用方管理，不应提交到版本库。

## 3. 接入已有流水线

调用 `tableledger.scope_guard.audit(question, answer, evidence, plans)` 可进行无网络的风险检查。`normalize_scope`校验结构化读取响应；`run_guard(question, doc, record, meter, root)`执行有界复核。

调用方的meter须提供 `client.model`、`call(messages, label=..., tokens=..., thinking=...)`；call返回文本响应，并负责预算、实际网络调用与原始响应存储。原图和已授权的示例只应发送到调用方允许的服务。

输入record包含answer、evidence、plans。返回结果包含answer、route、audit与readers。只有两次有效读取支持改变时才替换答案；其他情况保留输入答案。缓存目录必须由调用方隔离，升级后使用新的实现指纹。
