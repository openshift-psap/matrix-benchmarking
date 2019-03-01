import os
import subprocess
import inspect
import re
import measurement

class NvidiaTool:
    def __init__(self, experiment):
        self.cmd = 'nvidia-smi stats'
        self.kinds = {
            'memUtil': 'guest.gpu_memory',
            'gpuUtil': 'guest.gpu',
            'encUtil': 'guest.encode',
            'decUtil': 'guest.decode'
        }
        self.tables = {}
        for kind, field in self.kinds.items():
            self.tables[kind] = experiment.create_table(['time', field])

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
                self.tables[kind].add(time, value)

class IntelTool:
    def __init__(self):
        # TODO write our own with timing!
        self.cmd = 'intel_gpu_time sleep 80000'
    def parse_log(self, log):
        pass

class GPU(measurement.Measurement):
    # TODO accept a machine ??
    def __init__(self, cfg=None, **kargs):
        super().__init__(**kargs)
        self.log = 'gpu_stats.txt'
        self.cmd = None
        # TODO check the type of card (Intel/Nvidia/Others)
        # check commands (intel_gpu_time for Intel, nvidia-smi for
        # Nvidia. Use glxinfo or others to detect the card
        self.tool = NvidiaTool(self.experiment)

    def start(self):
        # TODO maybe write an utility
        try:
            os.unlink(self.log)
        except FileNotFoundError:
            pass
        # TODO launch the utility
        out = open(self.log, 'w')
        cmd = self.tool.cmd.split()
        #self.cmd = subprocess.Popen(cmd, stdout=out, close_fds=True)

    def stop(self):
        # TODO stop utility
        if self.cmd is not None:
            self.cmd.terminate()
            self.cmd.wait()

    def collect(self):
        # TODO I really should this about: 1) remote 2) table output!
        cur_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        self.log = os.path.join(cur_dir, '..', 'nvidia_example.txt')
        self.tool.parse_log(self.log)
        #os.unlink(self.log)
