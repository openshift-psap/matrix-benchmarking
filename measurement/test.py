import os
import subprocess
from datetime import datetime
from measurement import Measurement

class Test(Measurement):
    def __init__(self, cfg, experiment):
        Measurement.__init__(self, experiment)
        self.log = 'vmstat.log'
        self.vmstat = None
        # verify we have the command we need
        subprocess.check_call('vmstat --version'.split(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.table = self.experiment.create_table(['time', 'client.cpu'])
        subprocess.call('killall vmstat 2> /dev/null; rm -f %s' % self.log, shell=True)

    def start(self):
        try:
            os.unlink(self.log)
        except FileNotFoundError:
            pass
        # start vmstat
        out = open(self.log, 'w')
        self.vmstat = subprocess.Popen('vmstat -t 1'.split(), stdout=out, close_fds=True)
    def stop(self):
        self.vmstat.terminate()
        self.vmstat.wait()
    def collect(self):
        # parse log
        with open(self.log) as f:
            header = f.readline()
            if header.find('timestamp') < 0:
                raise Exception('Wrong vmstat header: ' + header)
            header = f.readline().split()
            idle_idx = header.index('id') # extract IDLE column
            time_idx = header.index('GMT') # extract TIMESTAMP column
            if len(header) != time_idx + 1:
                raise Exception('Timestamp not at the end')
            for line in f:
                fields = line.split()
                if line.find('timestamp') > 0:
                    f.readline()
                    continue
                cpu = 100 - int(fields[idle_idx])
                time = ' '.join(fields[-2:])
                time = int(datetime.strptime(time, '%Y-%m-%d %H:%M:%S').timestamp())
                self.table.add(time, cpu)
        os.unlink(self.log)
