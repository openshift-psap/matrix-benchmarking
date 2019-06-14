#!/bin/env python

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as pyplot
import numpy

class Plot(object):

    def __init__(self, x, y, title, y_label=None, x_label='time(s)'):
        self.x = self.zeroify(x)
        self.y = self.zeroify(y)
        self.x_label = x_label
        self.y_label = y_label
        self.title = title
    # __init__

    @staticmethod
    def zeroify(_list):
        return [i or 0 for i in _list]
    # zeroify
# Plot

class DataView(object):

    def __init__(self, data):
        self.data = data
    # __init__
# DataView

class GraphDataView(Gtk.ScrolledWindow, DataView):

    def __init__(self, data, plots=[]):
        DataView.__init__(self, data)
        Gtk.ScrolledWindow.__init__(self)
        self.plots = plots
        self.graph = None
        self.add_label_placeholder()
        self.connect("map", self.map_cb)
        self.connect("unmap", self.unmap_cb)
    # __init__

    def add_label_placeholder(self):
        text = self.data and "Loading..." or "No data provided"
        self.add(Gtk.Label("<i>%s</i>" % text, use_markup=True))
        self.show_all()
    # add_label_placeholder

    def map_cb(self, widget):
        if not self.data:
            return

        def plot_idle():
            nrows = len(self.plots)
            self.graph, axes = pyplot.subplots(nrows=nrows, sharex=True)
            self.graph.subplots_adjust(top=0.95, bottom=0.05, left=0.1, right=0.95, hspace=0.3)
            self.graph.align_ylabels()

            for i in xrange(nrows):
                a = axes[i]
                p = self.plots[i]
                a.set(title=p.title, ylabel=p.y_label)
                if i == nrows-1:
                    a.set_xlabel(p.x_label)
                a.grid()
                a.plot(p.x, p.y, '.-')

            canvas = FigureCanvas(self.graph)
            canvas.set_size_request(900, 700)
            self.remove(self.get_child())
            self.add_with_viewport(canvas)
            self.show_all()
            return False
        # plot_idle

        GLib.idle_add(plot_idle)
    # map_cb

    def unmap_cb(self, widget):
        if self.graph:
            pyplot.close(self.graph)
        self.remove(self.get_child())
        self.add_label_placeholder()
    # unmap_cb
# GraphDataView

class GuestDataView(GraphDataView):
    text = "Guest"

    def __init__(self, data):
        time = []
        gpu_mem = []
        gpu_usage = []
        encode_usage = []
        decode_usage = []

        for d in data:
            time.append(d.time)
            gpu_mem.append(d.gpu_memory)
            gpu_usage.append(d.gpu_usage)
            encode_usage.append(d.encode_usage)
            decode_usage.append(d.decode_usage)

        plots = [Plot(time, gpu_mem, "GPU Memory", "memory(MB)"),
                 Plot(time, gpu_usage, "GPU Usage", "usage(%)"),
                 Plot(time, encode_usage, "Encode Usage", "usage(%)"),
                 Plot(time, decode_usage, "Decode Usage", "usage(%)")]

        GraphDataView.__init__(self, data, plots)
    # __init__
# GuestDataView

class HostDataView(GraphDataView):
    text = "Host"

    def __init__(self, data):
        time = []
        cpu_usage = []

        for d in data:
            time.append(d.time)
            cpu_usage.append(d.cpu_usage)

        plots = [Plot(time, cpu_usage, "CPU Usage", "usage(%)")]
        GraphDataView.__init__(self, data, plots)
    # __init__
# HostDataView

class ClientDataView(GraphDataView):
    text = "Client"

    def __init__(self, data):
        time = []
        gpu_usage = []
        app_gpu_usage = []
        cpu_usage = []
        app_cpu_usage = []

        for d in data:
            time.append(d.time)
            gpu_usage.append(d.gpu_usage)
            app_gpu_usage.append(d.app_gpu_usage)
            cpu_usage.append(d.cpu_usage)
            app_cpu_usage.append(d.app_cpu_usage)

        plots = [Plot(time, gpu_usage, "GPU Usage", "usage(%)"),
                 Plot(time, app_gpu_usage, "App GPU Usage", "usage(%)"),
                 Plot(time, cpu_usage, "CPU Usage", "usage(%)"),
                 Plot(time, app_cpu_usage, "App CPU Usage", "usage(%)")]

        GraphDataView.__init__(self, data, plots)
    # __init__
# ClientDataView

class FramesDataView(GraphDataView):
    text = "Frames"

    def __init__(self, data):
        agent_time = []
        size = []
        mm_time = []
        capture_duration = []
        encode_duration = []
        send_duration = []
        client_time = []
        decode_duration = []
        queue_size = []

        for d in data:
            agent_time.append(d.agent_time)
            size.append(d.size)
            mm_time.append(d.mm_time)
            capture_duration.append(d.capture_duration)
            encode_duration.append(d.encode_duration)
            send_duration.append(d.send_duration)
            client_time.append(d.client_time)
            decode_duration.append(d.decode_duration)
            queue_size.append(d.queue_size)

        plots = [Plot(agent_time, size, "Size", "size(bytes)"),
                 Plot(agent_time, capture_duration, "Capture Duration", "duration(s)"),
                 Plot(agent_time, encode_duration, "Encode Duration", "duration(s)"),
                 Plot(agent_time, send_duration, "Send Duration", "duration(s)"),
                 Plot(agent_time, decode_duration, "Decode Duration", "duration(s)"),
                 Plot(agent_time, queue_size, "Queue Size", "frames(number)")]

        GraphDataView.__init__(self, data, plots)
    # __init__
# FramesDataView

class ExperimentDataView(Gtk.Grid, DataView):
    text = "Experiment"

    def __init__(self, data):
        DataView.__init__(self, data)
        Gtk.Grid.__init__(self,
                          border_width=10,
                          column_homogeneous=True,
                          column_spacing=10,
                          row_spacing=10)

        self.insert_column(0)
        self.insert_column(1)
        self.insert_column(2)

        row = 0
        for key, val in data:
            self.display_data(key, val, row)
            row += 1
        self.show_all()
    # __init__

    def display_data(self, text, value, row):
        self.insert_row(row)
        w = Gtk.Label("<b>%s:</b>" % text.capitalize(),
                      use_markup=True,
                      xalign=1.0)
        self.attach(w, 0, row, 1, 1)

        if not value:
            value = "<i>not provided</i>"

        w = Gtk.Label("%s" % value,
                      use_markup=True,
                      xalign=0.0)
        self.attach(w, 1, row, 2, 1)
    # display_data
# ExperimentDataView
