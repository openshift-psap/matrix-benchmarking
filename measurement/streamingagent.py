import os
import inspect
import re
from measurement import Measurement

class StreamingAgent(Measurement):
    def __init__(self, cfg, experiment):
        Measurement.__init__(self, experiment)
        self.log = 'streaming.log'
        self.table = self.experiment.create_table([
            'time',
            'guest.frame_size',
            'guest.capture_duration',
            'guest.encode_duration',
            'guest.send_duration',
        ])
        self.params = {}
        if cfg:
            if 'FPS' in cfg:
                fps = int(cfg['FPS'])
                self.experiment.set_param('FPS', fps)
                self.params['framerate'] = fps
            # TODO other parameters
        self.guest = self.experiment.machines['guest']
        cur_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        exe = os.path.join(cur_dir, '..', 'utils', 'execover')
        self.guest.upload(exe, '/usr/local/bin/execover')
        self.guest.run('chmod +x /usr/local/bin/execover && restorecon -Fv /usr/local/bin/execover')
        self.guest.run(['rm', '-f', '/tmp/streaming.log'])

    def start(self):
        # run streaming agent with log
        out = self.guest.run('pidof spice-streaming-agent')
        pid = -1
        for row in [row for row in out.split('\n') if row]:
            try:
                pid = int(row)
            except:
                pass
        assert pid > 0, "Process not found"
        params = ['-c %s=%s' % (k, v) for k, v in self.params.items()]
        params = ' '.join(params)
        cmd = '/usr/bin/spice-streaming-agent -l /tmp/streaming.log %s' % params
        cmd = '/usr/local/bin/execover %d %s' % (pid, cmd)
        self.guest.run(cmd)

    def stop(self):
        pass

    def collect(self):
        # retrieve
        self.guest.download('/tmp/streaming.log', self.log)
        self.guest.run(['rm', '-f', '/tmp/streaming.log'])

        # parse log
        line_re = re.compile(r'^(\d+): (\w+)(.*)')
        bytes_re = re.compile(r' of (\d+) ')
        new_stream_re = re.compile(r' new stream wXh (\d+)X(\d+) ')
        for line in open(self.log):
            m = line_re.match(line)
            if not m:
                continue
            time = int(m.group(1))
            verb = m.group(2)
            if verb == 'Capturing':
                start = time
                captured = None
                sent = None
                frame_bytes = None
            elif verb == 'Captured':
                captured = time
                encoded = time # old logs do not have encoding
            elif verb == 'Encoded':
                encoded = time
            elif verb == 'Frame':
                m = bytes_re.match(m.group(3))
                frame_bytes = int(m.group(1))
            elif verb == 'Sent':
                sent = time
                self.table.add(start / 1000000, frame_bytes,
                               (captured - start) / 1000000,
                               (encoded - captured) / 1000000,
                               (sent - encoded) / 1000000)
            elif verb == 'Started':
                m = new_stream_re.match(m.group(3))
                if m:
                    self.experiment.set_param('width', m.group(1))
                    self.experiment.set_param('height', m.group(2))

        os.unlink(self.log)
