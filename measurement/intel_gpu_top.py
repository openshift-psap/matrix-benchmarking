import datetime
import json

from . import mpstat

class Intel_GPU_Top(mpstat.SysStat):
    def __init__(self, cfg, experiment):
        self.cmd = 'sudo intel_gpu_top -J -s 1000'
        self.check_cmd = 'sudo intel_gpu_top -h'

        mpstat.SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(['gpu.time',
                                                   'gpu.render', 'gpu.blitter',
                                                   'gpu.video', 'gpu.videoenhance'])
        self.json_buffer = []
        self.open_parent = 0

    def process_buffer(self):
        json_txt = "".join(self.json_buffer)[:-1] # remove trailing ','
        try:
            json_desc = json.loads(json_txt)
        except: import pdb;pdb.set_trace()

        engines = ['Render/3D/0', 'Blitter/0', 'Video/0', 'VideoEnhance/0']

        entries = [json_desc['engines'][engine]['busy'] for engine in engines]

        self.table.add(int(datetime.datetime.now().timestamp()),
                       *entries)

    def process_line(self, line):
        if not line.strip():
            return

        self.json_buffer.append(line.strip())
        self.open_parent += line.count("{")
        self.open_parent -= line.count("}")

        if self.open_parent == 0:
            self.process_buffer()
            self.json_buffer[:] = []
