import subprocess
import time

def run_cmd(state, exe, cmd, addr=None):
    remote_cmd = f"ssh -t -t {addr} {cmd}" if addr else cmd

    if exe.dry:
        exe.log(f"stress-test: dry run: '{remote_cmd}'")
    else:
        exe.log(f"stress-test: run: '{remote_cmd}'")
        state.running.append(subprocess.Popen(remote_cmd, close_fds=True, shell=True,
                                          stdin=subprocess.DEVNULL))

cores_count = {}

def set_cpu(state, exe, cfg, machines):
    nb, syst = cfg.split("*")
    addr = machines[syst]

    if nb != "X":
        nb_cores = int(nb)
    else:
        # https://stackoverflow.com/questions/6481005/how-to-obtain-the-number-of-cpus-cores-in-linux-from-the-command-line
        COUNT_HYPER_THREADS = True

        nb_cores_cmd = "cat /proc/cpuinfo | grep -c ^processor /proc/cpuinfo" if COUNT_HYPER_THREADS \
            else "cat /proc/cpuinfo | grep '^core id' | sort -u | wc -l"

        try:
            nb_cores = cores_count[syst]
        except KeyError:
            nb_cores = int(subprocess.run(f"ssh {addr} {nb_cores_cmd}",
                                          capture_output=True, check=True, shell=True)\
                           .stdout\
                           .decode("ascii")[:-1])
            cores_count[syst] = nb_cores_cmd

    exe.log(f"stress-test: MAKE {nb_cores} CPU cores busy on system {syst}/{addr}",
            "(dry run)" if exe.dry else "")

    stress_cmd = f"stress --cpu {nb_cores}"

    run_cmd(state, exe, stress_cmd, addr)

def set_network(state, exe, cfg, machines):
    latency, bw = cfg.split("+")

    latency_server_cmd = "sudo /home/kevin/spice/latency/latency --server"
    latency_client_cmd = f"sudo /home/kevin/spice/latency/latency {latency} {bw} --client {machines['server']}"

    run_cmd(state, exe, latency_server_cmd, machines["server"])
    run_cmd(state, exe, latency_client_cmd, machines["client"])
    exe.wait(2)

    client_addr = machines["client"]
    LATENCY_ADDR = "192.168.127.1"
    CLIENT_NAME = "spicy"
    check_client_cmd = f"pgrep {CLIENT_NAME}.\*{LATENCY_ADDR} -f -c"

    while True and not exe.dry:
        running = subprocess.run(f'ssh {client_addr} "{check_client_cmd}"',
                                     capture_output=True, shell=True)\
                            .stdout\
                            .decode("ascii")[:-1]

        if int(running) == 0 or int(running) > 2:
            # the ssh/bash process should be counted ...
            import pdb;pdb.set_trace()
        if int(running) == 2: # the ssh/bash process is counted ...
            break

        msg = f"stress-test: WARNING: spicy not running/connected to {LATENCY_ADDR}"
        exe.log(msg)
        print(msg)

        time.sleep(2)


def do_killall(state, exe):
    if exe.dry:
        exe.log("stress-test: dry kill all the processes.")
        if state.running:
            exe.log("stress-test: ERROR: no processes should be running in dry mode ...")
        return

    while state.running:
        proc = state.running.pop()
        exe.log(f"stress-test: terminate {proc.args}")

        proc.terminate()
        try:
            # give a few seconds for the process to die peacefully
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            exe.log("stress-test: {p.args} had to be forcefully killed ...")
            proc.kill()

STRESS_SETTERS = {
    "cpu": set_cpu,
    "net": set_network,
}

def stress_test(state, exe, resources, machines):
    if not hasattr(state, "current"):
        state.current = None
        state.running = []

    def normal():
        state.current = None
        exe.log(f"stress-test: turn everything off.")
        do_killall(state, exe)

    exe.log("stress-test: new state:", resources)

    if resources == "normal":
        normal()
        return

    if state.current is not None:
        exe.log(f"stress-test: ERROR: previous state still in place ({state.current})")
        normal()

    state.current = resources

    # resources: guest:Xcpu/client:Xcpu
    for res_desc in resources.split("^"):
        # res_desc: guest:X*cpu
        res_type, res_cfg = res_desc.split(":")

        STRESS_SETTERS[res_type](state, exe, res_cfg, machines)
