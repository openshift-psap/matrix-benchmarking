import datetime

from . import mpstat

class PidStat(mpstat.SysStat):
    def __init__(self, cfg, experiment):
        mode = cfg['mode']
        self.cmd = f'pidstat -p {cfg["pid"]} 1'
        self.check_cmd = 'pidstat -V'

        mpstat.SysStat.__init__(self, cfg, experiment)

        self.table = self.experiment.create_table(["time",
                                                   f'{mode}-pid.cpu_user',
                                                   f'{mode}-pid.cpu_system'])

    def process_line(self, line):
        if self.headers is None:
            if "%CPU" in line:
                "02:58:42 PM   UID       PID    %usr %system  %guest   %wait    %CPU   CPU  Command"
                self.headers = ["time"] + line.split()[1:]
            return

        fields = dict(zip(self.headers, line.split()))

        try:
            time = int(datetime.datetime.strptime(' '.join([datetime.date.today().isoformat(),
                                                            fields["time"]]),
                                                  '%Y-%m-%d %H:%M:%S').timestamp())
            usr = float(fields["%usr"])
            sys = float(fields["%system"])
        except Exception as e:
            raise Exception("Faile to parse line '{line.strip()}'", e)

        self.table.add(time, usr, sys)
