import datetime
import os


from . import mpstat, hot_connect

class PidStat(mpstat.SysStat):
    def __init__(self, cfg, experiment):
        self.mode = cfg['mode']
        self.pid = cfg["pid"]
        self.cmd = f'pidstat -p {self.pid} 1'
        self.check_cmd = 'pidstat -V'

        mpstat.SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(["time",
                                                   f'{self.mode}-pid.cpu_user',
                                                   f'{self.mode}-pid.cpu_system'])

    def process_line(self, line):
        if self.headers is None:
            if "%CPU" in line:
                "02:58:42 PM   UID       PID    %usr %system  %guest   %wait    %CPU   CPU  Command"
                self.headers = ["time"] + line.split()[1:]
            return

        # printed when pidstat is terminated
        if "Average" in line: return
        if not line: return

        fields = dict(zip(self.headers, line.split()))

        try:
            time = int(datetime.datetime.strptime(' '.join([datetime.date.today().isoformat(),
                                                            fields["time"]]),
                                                  '%Y-%m-%d %H:%M:%S').timestamp())
            usr = float(fields["%usr"])
            sys = float(fields["%system"])
        except Exception as e:
            if not os.path.exists(f"/proc/{self.pid}"):
                print(f"PidStat: {self.mode}: {self.pid} is dead")

                hot_connect.detach_module(self)
                raise StopIteration()

            raise Exception(f"Failed to parse line '{line.strip()}'", e)

        self.table.add(time, usr, sys)
