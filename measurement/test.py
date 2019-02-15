import os
import subprocess
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
        # TODO parse log and save a table or something
        os.system("cat %s" % self.log)
        os.unlink(self.log)
