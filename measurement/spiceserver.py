import os
import re
from measurement import Measurement

# Log examples
# [59560 1554119595.056377] stream_device_data: Stream data packet size 34667 mm_time 2717827
# [59561 1554119595.056535] stream_channel_data: Stream data packet size 34667 mm_time 2717827

class SpiceServer(Measurement):
    def __init__(self, cfg, experiment):
        Measurement.__init__(self, experiment)
        self.log = 'host.log'
        self.table = self.experiment.create_table([
            'host.frame_size',
            'host.mm_time',
        ])
        self.remote_log = None
        if cfg:
            if 'log' in cfg:
                self.remote_log = str(cfg['log'])
        assert not self.remote_log is None, "Missing log configuration"
        self.host = self.experiment.machines['host']

    def start(self):
        # log should be already running
        pass

    def stop(self):
        pass

    def collect(self):
        # retrieve
        self.host.download(self.remote_log, self.log)

        # parse log
        line_re = \
            re.compile(r'^\[(\d+) ([0-9.]+)\] (\w+):? Stream data packet size (\d+) mm_time (\d+)')
        for line in open(self.log):
            m = line_re.match(line)
            if not m:
                continue
            # time = float(m.group(2))
            verb = m.group(3)
            frame_size = int(m.group(4))
            mm_time = int(m.group(5))
            if verb == 'stream_channel_data':
                # print(frame_size, mm_time)
                self.table.add(frame_size, mm_time)

        os.unlink(self.log)
