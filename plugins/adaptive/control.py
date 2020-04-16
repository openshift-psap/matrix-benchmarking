import os, json, socket

USE_VIRSH = None
VIRSH_VM_NAME = None
QMP_ADDR = None

def configure(plugin_cfg, machines):
    global USE_VIRSH, VIRSH_VM_NAME, QMP_ADDR

    USE_VIRSH = plugin_cfg['use_virsh']
    if USE_VIRSH:
        VIRSH_VM_NAME = plugin_cfg['virsh_vm_name']
    else:
        QMP_ADDR = machines['server'], plugin_cfg['qmp_port']

def apply_settings(driver_name, settings):
    settings_str = ",".join(f"{k}={v}" for k, v in settings.items() if v not in (None, ""))

    args = {"guest-encoder": driver_name,
            "guest-encoder-params": settings_str}
    try:
        args["target-fps"] = int(settings["framerate"])
    except KeyError: pass # no framerate available, ignore
    except ValueError as e:
        print("WARNING: invalid value for 'framerate':", e)

    _send_qmp(set_spice_args=args)

def request(msg, dry, log, client=False, agent=False, force=False):
    if not (client or agent):
        print(f"ERROR: send '{msg}' to nobody ...")
        return

    whom = (['agent'] if agent else []) + (['client'] if client else [])

    log(f"request: send '{msg}' to {', '.join(whom)}")
    if dry and not force: return

    rq = dict()
    if client: rq['client-request'] = msg
    if agent: rq['streaming-agent-request'] = msg

    _send_qmp(rq)

def reset_settings():
    return apply_settings("reset", {})

def _send_qmp(set_spice_args):
    json_msg = json.dumps(dict(execute="set-spice",
                               arguments=set_spice_args))

    if USE_VIRSH:
        cmd = f"virsh qemu-monitor-command {VIRSH_VM_NAME} '{json_msg}'"
        os.system(cmd)
        return

    qmp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    qmp_sock.connect(QMP_ADDR)
    qmp_sock.send('{"execute":"qmp_capabilities"}'.encode('ascii'))
    qmp_sock.send(json_msg.encode("ascii"))
    resp = ""
    to_read = 3
    while True:
        c = qmp_sock.recv(1).decode('ascii')
        if not c: break
        resp += c

        if c == '\n':
            if "error" in resp:
                print(resp)
            to_read -= 1; resp = ""
            if to_read == 0: break

    qmp_sock.close()
