"""Hash both the extension and the externally installed validation interfaces."""
import hashlib
import importlib
from pathlib import Path


def implementation_hash():
    names = ('fingerprint','scope_guard','blind_review','evidence','schema','regions',
             'documents','advanced_prompts','comparison','evaluation','prompts','fewshot')
    digest = hashlib.sha256()
    for name in names:
        module = importlib.import_module(__package__ + '.' + name)
        digest.update(name.encode())
        digest.update(Path(module.__file__).read_bytes())
    return digest.hexdigest()
