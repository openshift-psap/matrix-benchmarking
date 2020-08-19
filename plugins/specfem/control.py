import os, json, socket
from ui import InitialState, UIState

def configure(plugin_cfg, machines):
    pass

def apply_settings(driver_name, settings):
    conf = settings['conf']
    
    settings_str = conf.replace(":", "=").replace("_", ",")
    for k, v in settings.items():
        if k == "conf": continue
        settings_str += f",{k}={v}"
        
    msg = f"remote_ctrl:apply_settings:{driver_name}:{settings_str}"

    UIState().DB.expe.send_feedback(msg)

def request(req, dry, log):
    msg = f"remote_ctrl:request:{req}"
    UIState().DB.expe.send_feedback(msg)

def reset_settings():
    return request("reset", False, print, )
