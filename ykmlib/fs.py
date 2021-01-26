import json
import os


def makedirs(name, mode=0o777, exist_ok=True):
    os.makedirs(name or '.', mode=mode, exist_ok=exist_ok)


def makedirs_for(path):
    makedirs(os.path.dirname(path))


def dump_json(obj, path, encoding='utf-8', **kwargs):
    kwargs.setdefault('ensure_ascii', False)
    kwargs.setdefault('indent', 4)

    makedirs_for(path)
    with open(path, mode='w', encoding=encoding) as f:
        json.dump(obj, f, **kwargs)


def load_json(path, encoding='utf-8', **kwargs):
    if not os.path.isfile(path):
        return None
    with open(path, mode='r', encoding=encoding) as f:
        return json.load(f, **kwargs)
