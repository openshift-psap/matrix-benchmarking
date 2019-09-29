import os
import inspect
import re
import subprocess
import datetime

import measurement
import utils.live

class SysStat(measurement.Measurement):
    def __init__(self, cfg, experiment):
        measurement.Measurement.__init__(self, experiment)
        self.process = None

        subprocess.check_call(self.check_cmd.split(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        self.live = utils.live.LiveStream()
        self.headers = None

    def start(self):
        def preexec(): # Don't forward signals.
            os.setpgrp()

        self.process = subprocess.Popen(self.cmd.split(),  preexec_fn=preexec,
                                        stdout=subprocess.PIPE, close_fds=True,
                                        env=dict(S_TIME_FORMAT="ISO"))
        self.live.start(self.process.stdout)

    def stop(self):
        self.live.stop()
        self.process.kill()

    def process_line(self, line):
        raise NotImplementedError()

class MPStat(SysStat):
    def __init__(self, cfg, experiment):
        self.cmd = 'mpstat 1'
        self.check_cmd = 'mpstat -V'

        SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(['time', 'cpu.idle', "cpu.guest"])

    def process_line(self, line):
        if self.headers is None:
            if "%idle" in line:
                "02:01:05 PM CPU %usr %nice %sys %iowait %irq %soft %steal %guest %gnice %idle"
                self.headers = ["time"] + line.split()[1:]
            return

        fields = dict(zip(self.headers, line.split()))

        idle = float(fields["%idle"])
        guest = float(fields["%guest"])
        time = int(datetime.datetime.strptime(' '.join([datetime.date.today().isoformat(),
                                                        fields["time"]]),
                                              '%Y-%m-%d %H:%M:%S').timestamp())

        self.table.add(time, idle, guest)
