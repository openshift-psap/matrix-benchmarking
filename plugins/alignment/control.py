import os, json, socket
from ui import InitialState, UIState

def configure(plugin_cfg, machines):
    pass

def apply_settings(driver_name, settings):
    settings_str = ",".join(f"{k}={v}" for k, v in settings.items() if v not in (None, ""))

    msg = f"remote_ctrl:apply_settings:{driver_name}:{settings_str}"

    UIState().DB.expe.send_feedback(msg)

def request(req, dry, log):
    msg = f"remote_ctrl:request:{req}"
    UIState().DB.expe.send_feedback(msg)

def reset_settings(driver_name, settings):
    return request("reset", False, print, )
