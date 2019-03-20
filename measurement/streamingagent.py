import os
import inspect
import re
import measurement

class StreamingAgent(measurement.Measurement):
    def __init__(self, cfg=None, **kargs):
        super().__init__(**kargs)
        # TODO final file
        cur_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        self.log = os.path.join(cur_dir, '..', 'streaming.log')
        self.table = self.experiment.create_table([
            'time',
            'guest.frame_size',
            'guest.capture_duration',
            'guest.encode_duration',
            'guest.send_duration',
        ])

    def start(self):
        # TODO
        pass

    def stop(self):
        # TODO
        pass

    def collect(self):
        # TODO retrieve
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

        # os.unlink(self.log)
