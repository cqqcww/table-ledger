"""Offline installation and interface diagnostics."""
import argparse
import json
from . import schema, cloud, pipeline, documents, prompts, xlsxio
from .fingerprint import implementation_hash


def main():
    p = argparse.ArgumentParser();p.add_argument('command',choices=['check']);p.parse_args()
    required = [(schema, ['AnswerError','compact_json','json_loads','normalize_response','validate_structure']),
                (cloud,['StopRun']), (pipeline,['atomic_json']), (documents,['image_content']),
                (prompts,['COMMON']), (xlsxio,['Question'])]
    missing = [m.__name__+'.'+name for m, names in required for name in names if not hasattr(m,name)]
    if missing:
        raise SystemExit('Missing backend interfaces: '+', '.join(missing))
    print(json.dumps({'ready':True,'network_calls':0,'implementation':implementation_hash()}))


if __name__ == '__main__':main()
