"""Shared local generation arguments and release metadata."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
import json
from pathlib import Path


def arguments():
    parser = argparse.ArgumentParser(description='Render original synthetic tables into a new directory.')
    parser.add_argument('--output', type=Path, required=True, help='New or empty output directory')
    parser.add_argument('--font', type=Path, required=True, help='Locally available Chinese font; not redistributed')
    args = parser.parse_args()
    args.output, args.font = args.output.expanduser(), args.font.expanduser()
    if not args.font.is_file():
        parser.error('--font must point to an existing font file')
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error('--output must be a new or empty directory')
    return args


def finalize(root, dataset):
    path = root / 'benchmark.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['description'] = '原创程序生成的中文表格文档与问题；标准答案来自渲染前的逻辑源表。'
    data['license'] = 'AGPL-3.0-only'
    data['usage_status'] = 'development_and_regression; historical split labels retained, not an unseen evaluation set'
    if dataset == 'synthetic_v1':
        data['split_method'] = '按模板族隔离的历史划分：24文档144题dev，12文档72题holdout。当前均已用于开发或回归。'
    else:
        data['version'] = 'chinese-diagnostics-v1'
        data['limitations'] = '12份文档共享一个生成器和问题族；用于合成回归诊断，不能代表真实文档上的泛化。源表仅供核验，不进入视觉求解输入。'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
