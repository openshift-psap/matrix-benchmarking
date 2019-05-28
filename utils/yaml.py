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
        except:
            if not yml:
                raise
    return yml
