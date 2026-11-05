# 原创中文表格数据

本目录完整收录四套自建数据：**508 题、112 份文档**。所有题目与标准答案从渲染前的逻辑源表生成，文档原件保持原始字节；发布整理只补充说明、统一文档划分及使用状态，没有删题、改答案或重新渲染原件。

代码、原件与标注采用 [AGPL-3.0-only](../LICENSE)，Copyright (C) 2026 cqqcww and contributors。生成用字体不随仓库分发。

## 规模与题型

| 子集 | 文档 | 提取 | 推理 | 结构 | 总题数 |
|---|---:|---:|---:|---:|---:|
| `synthetic_v1` | 36 | 108 | 72 | 36 | 216 |
| `chinese_diagnostics_v1` | 12 | 36 | 24 | 0 | 60 |
| `layout_diagnostics_v1` | 24 | 72 | 0 | 0 | 72 |
| `structure_diagnostics_v2` | 40 | 120 | 0 | 40 | 160 |
| 合计 | **112** | **336** | **96** | **76** | **508** |
| 占全部题目 | | **66.14%** | **18.90%** | **14.96%** | **100%** |

文档包含 99 张 PNG 和 13 份双页 PDF。结构题均为局部恢复，要求完整表格的行列数及指定范围内的真实单元格，不是整表转录题。`extract` 中含 192 道行列数或表头层数题；该分组不意味着每个答案都能直接复制自某个单元格。题型比例描述这套数据自身，不代表其他业务场景。

按答案形状区分：数值 324 题（63.78%），有序数组 108 题（21.26%），结构对象 76 题（14.96%）。各百分比独立四舍五入。

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
  layout_diagnostics_v1/
    benchmark.json                 # 24份源表、72题及标准答案
    files/                         # 20张PNG、4份双页PDF
  structure_diagnostics_v2/
    benchmark.json                 # 40份源表、160题及标准答案
    files/                         # 34张PNG、6份双页PDF
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
| `split` | `train`、`dev`、`holdout` 或 `confirmation`；需结合使用状态解读 |

部分题目还有模板族、来源组或图像摘要字段，原样保留。`documents` 保存文档文件名、SHA-256、逻辑源表、合并信息、单位及生成参数。源表中的 `null` 表示被合并覆盖的位置；空字符串表示真实空白，两者不同。

两套几何子集还保留 `source.cells`、完整行列数、表头层数和每页对应的逻辑行清单。新增 `source.rows` / `source.merges` 是对这些原始单元格的等价展开，便于统一检查。跨页重复表头映射回同一批逻辑行。第四套的 `generation_split` 仅记录计数题生成时的旧标签，运行划分应使用按文档统一的 `split`。

`synthetic_v1` 的 `source.rows` 已按显示列顺序排列。`chinese_diagnostics_v1` 的 `source.rows` 是生成时的逻辑顺序，`source.column_order` 表示显示时每一列对应的原始列索引；核验图像位置时先应用该排列。不能直接把逻辑列号当成图片中的列位置。

## 历史划分与当前使用

| 子集 | 历史标签 | 文档 | 题数 | 目前用途 |
|---|---|---:|---:|---|
| `synthetic_v1` | `dev` | 24 | 144 | 开发与回归 |
| `synthetic_v1` | `holdout` | 12 | 72 | 已使用的历史验证数据，现作回归 |
| `chinese_diagnostics_v1` | `holdout` | 12 | 60 | 已使用的诊断数据，现作回归 |
| `layout_diagnostics_v1` | `dev` / `confirmation` | 18 / 6 | 54 / 18 | 两部分都已使用，现作回归 |
| `structure_diagnostics_v2` | `train` | 6 | 24 | 两份文档的结构题已作视觉示例；其余预留为训练 |
| `structure_diagnostics_v2` | `dev` | 10 | 40 | 10道结构题已评测；另30道计数题未单独评测，但来源已观察 |
| `structure_diagnostics_v2` | `confirmation` | 24 | 96 | 24道结构题与72道计数题尚未推理，来源整体保留 |

以上使用状态更新于 2026-11-05。第一套按模板族划分，同族三个变体留在同一侧；第二套共享部门结算生成器和五种问法；后两套共享几何生成器家族。保留历史标签是为了复现，**不代表仍未被观察或用于开发**。新的泛化验证应另外冻结来源和模板，不把同一文档中的不同题随机分到不同集合。公开的确认部分也不能当作永久保密的数据。

已使用的方向包括直接读取、合并表头与结构检查、空白和编号保护、单位换算、数组范围与顺序核验、独立重读、提示示例及版本回归。本文只记录数据和使用方法，不列模型表现。

## 检查与接入

仓库根目录执行，无需安装扩展后端：

```bash
python benchmarks/manage.py verify
python benchmarks/manage.py stats
python benchmarks/manage.py stats --dataset synthetic_v1
python benchmarks/manage.py export --output /tmp/table-ledger-inputs.jsonl
python benchmarks/manage.py export --dataset synthetic_v1 --split dev --output /tmp/table-ledger-dev.jsonl
python benchmarks/manage.py export --dataset structure_diagnostics_v2 --split confirmation --output /tmp/table-ledger-structure-confirmation.jsonl
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
python benchmarks/generators/geometry.py --suite layout --font /path/to/chinese-font.ttf --output /tmp/table-ledger-geometry
python benchmarks/generators/geometry.py --suite structure --font /path/to/chinese-font.ttf --output /tmp/table-ledger-structure
```

初始版式集使用基准种子 `84673`，部门集使用 `730031` 到 `730042`，几何计数集使用 `518231` 到 `518254`，新增结构集使用 `619031` 到 `619070`。脚本保留原题目与数值生成逻辑，拒绝覆盖非空目录。字体、渲染依赖及 PDF 元数据可能影响文件字节，因此重建文件的摘要不保证等同仓库原件；应记录为新渲染版本，并重新检查裁切、文字完整性和源表一致性。生成所需字体由使用者按其许可自行提供。

几何计数和新增结构集中的汇总数值是装饰性随机数据，不用于算术评测。需要数值运算测试时使用前两套相应题目，不能自行假定后两套汇总数字等于明细之和。

这些都是合成业务表，内容和问法较窄。像素文件中的文字来自排版渲染，不等同真实扫描、复杂拍照或手写文档。源表是核验依据；对模型预测的表格转录，不能仅因格式合法就认定读取正确。
