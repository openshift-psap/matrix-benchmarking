import os
import subprocess
import datetime
import measurement

class Test(measurement.Measurement):
    def start(self):
        self.log = 'vmstat.log'
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
                cpu = 100 - int(fields[idle_idx])
                time = ' '.join(fields[-2:])
                time = int(datetime.datetime.strptime(time, '%Y-%m-%d %H:%M:%S').timestamp())
                # TODO save a table
                print(time, cpu)
        os.unlink(self.log)
