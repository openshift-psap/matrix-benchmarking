import os
import subprocess
import inspect
import re
from measurement import Measurement

class NvidiaTool:
    def __init__(self, experiment, machine, is_guest=True):
        if is_guest:
            self.kinds = {
                'memUtil': 'guest.gpu_memory',
                'gpuUtil': 'guest.gpu',
                'encUtil': 'guest.encode',
                'decUtil': 'guest.decode'
            }
        else:
            self.kinds = {
                'gpuUtil': 'client.gpu',
            }
        self.machine = machine
        self.tables = {}
        for kind, field in self.kinds.items():
            self.tables[kind] = experiment.create_table(['time', field])
        machine.run(['rm', '-f', '/tmp/nvidia_stats.log'])

    def start(self):
        cmd = 'nvidia-smi stats > /tmp/nvidia_stats.log'
        self.process = self.machine.Process(cmd)

    def stop(self):
        self.process.terminate()
        del self.process

    def collect(self, log):
        # retrieve
        self.machine.download('/tmp/nvidia_stats.log', log)
        self.machine.run(['rm', '-f', '/tmp/nvidia_stats.log'])

        self.parse_log(log)

    def parse_log(self, log):
        line_re = re.compile(r'^\d+,\s*(pwrDraw|decUtil|encUtil|gpuUtil|temp|memUtil'
                             r'|violPwr|violThm|memClk|procClk)\s*,\s*(\d+),\s*(\d+)$')
        kinds = set(self.kinds.keys())
        start_time = None
        for line in open(log):
            # some versions fill some values with invalid values, skip
            # these lines
            if line.rfind('N/A, N/A') >= 0:
                continue
            m = line_re.match(line)
            if not m:
                raise Exception('Invalid line %s' % line)
            kind = m.group(1)
            time = int(m.group(2))
            value = int(m.group(3))
            if kind in kinds:
                if start_time is None:
                    start_time = time
                    start_time = start_time - start_time % (86400 * 1000000)
                self.tables[kind].add((time - start_time)/ 1000000, value)

class IntelTool:
    def __init__(self, experiment, machine):
        # TODO write our own with timing!
        self.cmd = 'intel_gpu_time sleep 80000'
    def start(self):
        # TODO
        pass
    def stop(self):
        # TODO
        pass
    def collect(self, log):
        # TODO
        pass

class GPU(Measurement):
    # TODO accept a machine ??
    def __init__(self, cfg, experiment):
        Measurement.__init__(self, experiment)
        self.log = 'gpu_stats.txt'
        # TODO check the type of card (Intel/Nvidia/Others)
        # check commands (intel_gpu_time for Intel, nvidia-smi for
        # Nvidia. Use glxinfo or others to detect the card
        machine_name = 'guest'
        if cfg:
            machine_name = cfg.get('machine', 'guest')
        is_guest = machine_name == 'guest'
        machine = self.experiment.machines[machine_name]
        self.tool = NvidiaTool(self.experiment, machine, is_guest)

    def start(self):
        self.tool.start()

    def stop(self):
        self.tool.stop()

    def collect(self):
        self.tool.collect(self.log)
        os.unlink(self.log)
