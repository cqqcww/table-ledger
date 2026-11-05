"""Evidence-bound extensions; the separately supplied backend is not distributed."""
import importlib
import os
from pathlib import Path
import sys

__version__ = '0.1.0'
root = os.environ.get('TABLELEDGER_BACKEND_ROOT')
if root:
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError('TABLELEDGER_BACKEND_ROOT is not a directory')
    sys.path.insert(0, str(path))
package = os.environ.get('TABLELEDGER_BACKEND_PACKAGE', 'tableqa')
for name in ('schema', 'cloud', 'pipeline', 'documents', 'prompts', 'xlsxio'):
    try:
        module = importlib.import_module(package + '.' + name)
    except ImportError as exc:
        raise ImportError('A compatible external backend is required. Set TABLELEDGER_BACKEND_ROOT; see INSTALL.md.') from exc
    sys.modules[__name__ + '.' + name] = module
