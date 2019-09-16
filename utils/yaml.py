from __future__ import absolute_import
import yaml

# from https://stackoverflow.com/questions/823196/yaml-merge-in-python
def merge(user, default):
    if isinstance(user,dict) and isinstance(default,dict):
        for k,v in default.items():
            if k not in user:
                user[k] = v
            else:
                user[k] = merge(user[k],v)
    return user

def load_multiple(*args):
    yml = None
    for arg in args:
        try:
            cfg = None
            with open(arg, 'r') as f:
                cfg = yaml.safe_load(f)
            if yml:
                yml = merge(yml, cfg)
            else:
                yml = cfg
        except Exception:
            if not yml:
                raise
    return yml

def subyaml(yml, path):
    if not yml:
        return yml
    for k in path.split('/'):
        if type(yml) != dict:
            return None
        yml = yml.get(k)
        if not yml:
            break
    return yml

def set_subyaml(yml, path, value):
    if not yml:
        return yml
    for k in path.split('/')[:-1]:
        y = None
        if type(yml) == dict:
            y = yml.get(k)
        # special case, could be a list of single strings/dictionaries
        elif type(yml) == list:
            for i in yml:
                if type(i) == dict:
                    l = list(i.keys())
                    if len(l) == 1 and l[0] == k:
                        y = i[l[0]]
        yml = y
        assert yml is not None, 'Path %s not found' % path
    assert type(yml) == dict
    name = path.split('/')[-1:][0]
    yml[name] = value
