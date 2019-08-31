import os
import subprocess
from datetime import datetime

import measurement
import utils.live

class VMStat(measurement.Measurement):
    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)
        self.process = None

        # verify we have the command we need
        subprocess.check_call('vmstat --version'.split(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self.table = self.experiment.create_table(['time', 'sys.mem_free'])
        self.live = utils.live.LiveStream()
        self.headers = []

    def start(self):
        # start vmstat
        self.process = subprocess.Popen('vmstat -t 1'.split(), stdout=subprocess.PIPE, close_fds=True)
        self.live.start(self.process.stdout)

    def stop(self):
        self.live.stop()
        self.process.kill()

    def process_line(self, line):
        if "memory" in line: return # first header line
        if "free" in line: # second header line
            "r b swpd free buff cache si so bi bo in cs us sy id wa st CEST"

            self.headers = line.split()
            self.headers.pop() # tz

            self.headers += ["date", "time"]
            return

        assert self.headers

        fields = dict(zip(self.headers, line.split()))

        time = int(datetime.strptime(' '.join([fields["date"], fields["time"]]),
                                     '%Y-%m-%d %H:%M:%S').timestamp())

        free = int(fields["free"])

        self.table.add(time, free)
