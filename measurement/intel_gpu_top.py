import datetime
import json
import subprocess
import os

from . import mpstat

class Intel_GPU_Top(mpstat.SysStat):
    def __init__(self, cfg, experiment):
        self.cmd = 'sudo intel_gpu_top -J -s 1000'
        self.check_cmd = 'intel_gpu_top -h'

        mpstat.SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(['gpu.time',
                                                   'gpu.render', 'gpu.blitter',
                                                   'gpu.video', 'gpu.videoenhance'])
        self.json_buffer = []
        self.open_parent = 0

    def process_buffer(self):
        json_txt = "".join(self.json_buffer)[:-1] # remove trailing ','

        json_desc = json.loads(json_txt)

        engines = ['Render/3D/0', 'Blitter/0', 'Video/0', 'VideoEnhance/0']

        entries = [json_desc['engines'][engine]['busy'] for engine in engines]

        self.table.add(int(datetime.datetime.now().timestamp()),
                       *entries)

    def stop(self):
        if not self.live: return

        if self.process.poll() is None:
            subprocess.check_call("sudo killall intel_gpu_top".split())

        self.live.stop()

    def process_line(self, line):
        if not line.strip():
            return

        self.json_buffer.append(line.strip())
        self.open_parent += line.count("{")
        self.open_parent -= line.count("}")

        if self.open_parent == 0:
            try:
                self.process_buffer()
            except json.decoder.JSONDecodeError:
                self.stop()

            self.json_buffer[:] = []
