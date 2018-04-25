#!/usr/bin/env python

import re

class Frame:
    def __init__(self, start):
        self.start = start
        self.decode = 0
        self.render = 0
    def __repr__(self):
        return "[%.3f, %.3f]" % (
            (self.captured - self.start) / 1000.0,
            (self.sent - self.captured) / 1000.0
        )

# parse streaming logs
line_re = re.compile(r'^(\d+): (\w+)(.*)')
bytes_re = re.compile(r' of (\d+) ')
min_time = 2**64
max_time = 0
frames = []
for line in open('streaming.log'):
    m = line_re.match(line)
    if m:
        time = int(m.group(1))
        min_time = min(min_time, time)
        max_time = max(max_time, time)
        verb = m.group(2)
        if verb == 'Capturing':
            frame = Frame(time)
        elif verb == 'Captured':
            frame.captured = time
        elif verb == 'Sent':
            frame.sent = time
            frames.append(frame)
            del frame
        elif verb == 'Frame':
            m = bytes_re.match(m.group(3))
            frame.bytes = int(m.group(1))
        else:
            print line

# parse nvidia log
line_re = \
re.compile(r'^\d+,\s*(pwrDraw|decUtil|encUtil|gpuUtil|temp|memUtil|violPwr|violThm|memClk|procClk)\s*,\s*(\d+),\s*(\d+)$')
min_time2 = 2**64
max_time2 = 0
nvidia_stats = []
for line in open('nvidia_stats.txt'):
    m = line_re.match(line)
    if not m:
        raise Exception('Invalid line %d' % line)
    kind = m.group(1)
    time = int(m.group(2))
    value = int(m.group(3))
    min_time2 = min(min_time2, time)
    max_time2 = max(max_time2, time)
    if kind in ['gpuUtil', 'memUtil', 'decUtil', 'encUtil']:
        nvidia_stats.append((kind, time, value))

# parse remote-viewer log
# Frame: 4829 10.31 decode 0.03 render
line_re = re.compile(r'Frame: \d+ ([.0-9]+) decode ([.0-9]+) render')
n = 0
for line in open('remote_viewer.txt'):
    m = line_re.match(line)
    if m:
        frames[n].decode = float(m.group(1))
        frames[n].render = float(m.group(2))
    n += 1


# normalize time for Nvidia stats
ratio = float(max_time - min_time) / (max_time2 - min_time2)
nvidia_stats = [(a[0], int((a[1] - min_time2) * ratio + min_time), a[2]) for a in nvidia_stats]

row_keys = []
class Row:
    def __init__(self):
        self.values = {}
    def __setitem__(self, key, value):
        self.values[key] = value
        if not key in row_keys:
            row_keys.append(key)
    def __repr__(self):
        return ','.join([str(self.values.get(key, '')) for key in row_keys])

class Rows(dict):
    def __missing__(self, key):
        self[key] = Row()
        return self[key]

rows = Rows()
for frame in frames:
    rows[frame.start]['capture'] = frame.captured - frame.start
    rows[frame.start]['sent'] = frame.sent - frame.captured
    rows[frame.start]['bytes'] = frame.bytes
    rows[frame.start]['decode'] = frame.decode
    rows[frame.start]['render'] = frame.render

for nvidia_stat in nvidia_stats:
    time = nvidia_stat[1]
    rows[time][nvidia_stat[0]] = nvidia_stat[2]

f = open('out.cvs', 'w')
f.write('time,' + ','.join(row_keys) + '\n')
for row in sorted(rows.iterkeys()):
    f.write('%d,%s\n' % (row, rows[row]))
