import os
import subprocess
from datetime import datetime

import measurement
import utils.live
from . import mpstat

class VMStat(mpstat.SysStat):
    def __init__(self, cfg, experiment):
        self.cmd = 'vmstat -t 1'
        self.check_cmd = 'vmstat --version'

        mpstat.SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(['time', 'sys.mem_free'])

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
