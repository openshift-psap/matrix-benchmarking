import os
import subprocess
import inspect
import re
from measurement import Measurement

class NvidiaTool:
    def __init__(self, experiment, machine):
        self.kinds = {
            'memUtil': 'guest.gpu_memory',
            'gpuUtil': 'guest.gpu',
            'encUtil': 'guest.encode',
            'decUtil': 'guest.decode'
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
        for line in open(log):
            m = line_re.match(line)
            if not m:
                raise Exception('Invalid line %d' % line)
            kind = m.group(1)
            time = int(m.group(2))
            value = int(m.group(3))
            if kind in kinds:
                self.tables[kind].add(time / 1000000, value)

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
    def __init__(self, cfg=None, **kargs):
        Measurement.__init__(self, **kargs)
        self.log = 'gpu_stats.txt'
        # TODO check the type of card (Intel/Nvidia/Others)
        # check commands (intel_gpu_time for Intel, nvidia-smi for
        # Nvidia. Use glxinfo or others to detect the card
        # TODO should be configurable
        self.guest = self.experiment.machines['guest']
        self.tool = NvidiaTool(self.experiment, self.guest)

    def start(self):
        self.tool.start()

    def stop(self):
        self.tool.stop()

    def collect(self):
        self.tool.collect(self.log)
        os.unlink(self.log)
