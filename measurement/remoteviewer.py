import os
import inspect
import re
from measurement import Measurement

class RemoteViewer(Measurement):
    def __init__(self, cfg, experiment):
        Measurement.__init__(self, experiment)
        self.log = 'rv.log'
        self.table = self.experiment.create_table([
            'client.mm_time',
            'client.frame_size',
            'client.time',
            'client.decode_duration',
            'client.queue',
        ])
        self.exe = 'remote-viewer'
        self.url = 'spice://localhost:5900'
        if cfg:
            if 'executable' in cfg:
                self.exe = str(cfg['executable'])
            if 'URL' in cfg:
                self.url = str(cfg['URL'])
        self.client = self.experiment.machines['client']
        self.client.run(['rm', '-f', '/tmp/rv.log'])
        self.client.run('rm -f /tmp/spice-gtk-gst-pipeline-debug-*.dot')
        self.client.run('killall remote-viewer || true')
        self.process = None

    def start(self):
        # run streaming agent with log
        cmd = '%s %s' % (self.exe, self.url)
        cmd = ('env RECORDER_TRACES="@output=/tmp/rv.log:frames_stats"'
               ' GST_DEBUG_DUMP_DOT_DIR=/tmp %s' % cmd)
        self.process = self.client.Process(cmd)

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(2)
        except:
            pass
        self.process.kill()
        self.process = None

    def collect(self):
        # retrieve
        self.client.download('/tmp/rv.log', self.log)
        out = self.client.run('ls -1 /tmp/spice-gtk-gst-pipeline-debug-*.dot || true')
        files = [row for row in out.split('\n') if row]
        dot_file = None
        if len(files):
            dot_file = 'rv.dot'
            self.client.download(files[0], dot_file)
        self.client.run('rm -f /tmp/spice-gtk-gst-pipeline-debug-*.dot')
        self.client.run(['rm', '-f', '/tmp/rv.log'])

        # read dot file
        if dot_file:
            with open(dot_file, 'r') as f:
                content = f.read()
                self.experiment.add_attachment('viewer pipeline', content)

        # parse log
        line_re = re.compile(r'.*frame mm_time (\d+) size (\d+)'
                             r' creation time (\d+) decoded time (\d+)'
                             r' queue (\d+)')
        for line in open(self.log):
            m = line_re.match(line)
            if m:
                fields = [int(m.group(i)) for i in range(1, 6)]
                fields[2] /= 1000000
                fields[3] /= 1000000
                self.table.add(*fields)

        os.unlink(self.log)
        if dot_file:
            os.unlink(dot_file)
