# 原创中文表格数据

本目录完整收录两套自建数据：**276 题、48 份文档**。所有题目与标准答案从渲染前的逻辑源表生成，文档原件保持原始字节；发布整理只调整说明和使用状态元数据，没有删题、改答案或重新渲染原件。

代码、原件与标注采用 [AGPL-3.0-only](../LICENSE)，Copyright (C) 2026 cqqcww and contributors。生成用字体不随仓库分发。

## 规模与题型

| 子集 | 文档 | 提取 | 推理 | 结构 | 总题数 |
|---|---:|---:|---:|---:|---:|
| `synthetic_v1` | 36 | 108 | 72 | 36 | 216 |
| `chinese_diagnostics_v1` | 12 | 36 | 24 | 0 | 60 |
| 合计 | **48** | **144** | **96** | **36** | **276** |
| 占全部题目 | | **52.17%** | **34.78%** | **13.04%** | **100%** |

文档包含 45 张 PNG 和 3 份双页 PDF。结构题均为局部恢复，要求完整表格的行列数及指定范围内的真实单元格，不是整表转录题。题型比例描述这套数据自身，不代表其他业务场景。

按答案形状区分：数值 132 题（47.83%），有序数组 108 题（39.13%），结构对象 36 题（13.04%）。各百分比独立四舍五入。

## 文件与字段

```text
benchmarks/
  manifest.json                    # 全集规模、使用状态与元数据摘要
  manage.py                        # 无后端依赖的检查、统计和输入导出
  requirements.txt                 # 仅重建图片/PDF时需要
  generators/                      # 原创生成源码
  synthetic_v1/
    benchmark.json                 # 36份源表、216题及标准答案
    files/                         # 33张PNG、3份双页PDF
  chinese_diagnostics_v1/
    benchmark.json                 # 12份源表、60题及标准答案
    files/                         # 12张PNG
```

`benchmark.json` 的 `questions` 是完整题目列表：

| 字段 | 含义 |
|---|---|
| `id` | 全集唯一题号，保持原值 |
| `file_name` | 同目录 `files/` 下的文档名 |
| `question_type` | `extract`、`thinking` 或 `structure` |
| `question` | 题目原文 |
| `table_hint` | 目标表提示 |
| `answer_format` | `number`、`json_array` 或 `json` |
| `expected` | 标准答案，仅用于核验 |
| `split` | 历史 `dev` / `holdout` 划分 |

部分题目还有模板族、来源组或图像摘要字段，原样保留。`documents` 保存文档文件名、SHA-256、逻辑源表、合并信息、单位及生成参数。源表中的 `null` 表示被合并覆盖的位置；空字符串表示真实空白，两者不同。

`synthetic_v1` 的 `source.rows` 已按显示列顺序排列。`chinese_diagnostics_v1` 的 `source.rows` 是生成时的逻辑顺序，`source.column_order` 表示显示时每一列对应的原始列索引；核验图像位置时先应用该排列。不能直接把逻辑列号当成图片中的列位置。

## 历史划分与当前使用

| 子集 | 历史标签 | 文档 | 题数 | 目前用途 |
|---|---|---:|---:|---|
| `synthetic_v1` | `dev` | 24 | 144 | 开发与回归 |
| `synthetic_v1` | `holdout` | 12 | 72 | 已使用的历史验证数据，现作回归 |
| `chinese_diagnostics_v1` | `holdout` | 12 | 60 | 已使用的诊断数据，现作回归 |

第一套按模板族划分，同族三个变体留在同一侧；第二套共享部门结算生成器和五种问法。当前两套都已参与本项目迭代，保留历史标签是为了复现，**不代表仍未被观察或用于开发**。以后做新的泛化验证，应另外冻结来源和模板，不把同一文档中的不同题随机分到不同集合。

已使用的方向包括直接读取、合并表头与结构检查、空白和编号保护、单位换算、数组范围与顺序核验、独立重读、提示示例及版本回归。本文只记录数据和使用方法，不列模型表现。

## 检查与接入

仓库根目录执行，无需安装扩展后端：

```bash
python benchmarks/manage.py verify
python benchmarks/manage.py stats
python benchmarks/manage.py stats --dataset synthetic_v1
python benchmarks/manage.py export --output /tmp/table-ledger-inputs.jsonl
python benchmarks/manage.py export --dataset synthetic_v1 --split dev --output /tmp/table-ledger-dev.jsonl
```

检查涵盖全集题号唯一性、文档引用、文件集合与 SHA-256、源表合并关系、答案形状和结构边界。导出路径必须尚不存在，避免覆盖文件；重复导出时指定新文件名。

导出记录包含 `id`、`file_name`、`question_type`、`question`、`table_hint`、`answer_format` 和相对仓库根目录的 `document_path`。将题目与对应图像/PDF交给自己的读取接口；记录每题输出后，单独从 `benchmark.json` 加载 `expected` 做核验。**不要将整个 `benchmark.json` 直接放入视觉求解提示**，其中含标准答案和渲染前的源表。

处理答案时保留数组顺序、重复项、前导零编号、空白、零和横杠的区别。数值题按题目单位及精度处理；结构坐标从零开始，合并单元格只输出一次，局部范围仍使用完整逻辑行列数。

## 从源码重建

现有原件可以直接使用。若需重新渲染，在具备中文字体的本地环境安装生成依赖，并输出到新目录：

```bash
python -m pip install -r benchmarks/requirements.txt
python benchmarks/generators/layouts.py --font /path/to/chinese-font.ttf --output /tmp/table-ledger-layouts
python benchmarks/generators/departments.py --font /path/to/chinese-font.ttf --output /tmp/table-ledger-departments
```

版式集使用基准种子 `84673`，部门集使用 `730031` 到 `730042`。脚本保留原题目与数值生成逻辑，拒绝覆盖非空目录。字体、渲染依赖及 PDF 元数据可能影响文件字节，因此重建文件的摘要不保证等同仓库原件；应记录为新渲染版本，并重新检查裁切、文字完整性和源表一致性。生成所需字体由使用者按其许可自行提供。

这些都是合成业务表，内容和问法较窄。像素文件中的文字来自排版渲染，不等同真实扫描、复杂拍照或手写文档。源表是核验依据；对模型预测的表格转录，不能仅因格式合法就认定读取正确。
