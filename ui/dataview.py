#!/bin/env python

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar
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

class PlotMetaData(object):

    def __init__(self, x_attr, y_attr):
        self.x_attr = x_attr
        self.x_data = []
        self.y_attr = []
        self.y_data = []
        self.title = []
        self.label = []
        self.plots = []
        self.num_plots = len(y_attr)

        for i in range(self.num_plots):
            self.y_data.append([])
            self.y_attr.append(y_attr[i][0])
            self.title.append(y_attr[i][1])
            self.label.append(y_attr[i][2])
    #__init__

    def process_data(self, data):
        if not self.plots:
            for d in data:
                self.x_data.append(getattr(d, self.x_attr))
                for i in range(self.num_plots):
                    self.y_data[i].append(getattr(d, self.y_attr[i]))

            for i in range(self.num_plots):
                self.plots.append(Plot(self.x_data, self.y_data[i], self.title[i], self.label[i]))

        return self.plots
    # process_data
# PlotMetaData

class DataView(object):

    def __init__(self, data):
        self.data = data
    # __init__
# DataView

class GraphDataView(Gtk.ScrolledWindow, DataView):

    def __init__(self, data):
        DataView.__init__(self, data)
        Gtk.ScrolledWindow.__init__(self)
        self.graph = None
        self.set_label_placeholder("Loading...")
        self.connect("map", self.map_cb)
        self.connect("unmap", self.unmap_cb)
    # __init__

    def set_label_placeholder(self, text):
        child = self.get_child()
        if child:
            self.remove(child)
        self.add(Gtk.Label("<i>%s</i>" % text, use_markup=True))
        self.show_all()
    # set_label_placeholder

    def map_cb(self, widget):
        if not self.data:
            self.set_label_placeholder("No data provided")
            return

        plots = self.metadata.process_data(self.data)

        def plot_idle():
            nrows = len(plots)
            self.graph, axes = pyplot.subplots(nrows=nrows, sharex=True)
            self.graph.subplots_adjust(top=0.95, bottom=0.05, left=0.1, right=0.95, hspace=0.3)
            self.graph.align_ylabels()

            for i in range(nrows):
                a = axes[i]
                p = plots[i]
                a.set(title=p.title, ylabel=p.y_label)
                if i == nrows-1:
                    a.set_xlabel(p.x_label)
                a.grid()
                a.plot(p.x, p.y, '.-')

            canvas = FigureCanvas(self.graph)
            canvas.set_size_request(900, 700)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            vbox.pack_start(canvas, True, True, 0)
            toolbar = NavigationToolbar(canvas, self.get_toplevel())
            vbox.pack_start(toolbar, False, True, 0)

            self.remove(self.get_child())
            self.add_with_viewport(vbox)
            self.show_all()
            return False
        # plot_idle

        GLib.idle_add(plot_idle)
    # map_cb

    def unmap_cb(self, widget):
        if self.graph:
            pyplot.close(self.graph)
        self.set_label_placeholder("Loading...")
    # unmap_cb
# GraphDataView

class GuestDataView(GraphDataView):
    text = "Guest"
    metadata = PlotMetaData("time", [("gpu_memory", "GPU Memory", "memory(MB)"),
                                     ("gpu_usage", "GPU Usage", "usage(%)"),
                                     ("encode_usage", "Encode Usage", "usage(%)"),
                                     ("decode_usage", "Decode Usage", "usage(%)")])
# GuestDataView

class HostDataView(GraphDataView):
    text = "Host"
    metadata = PlotMetaData("time", [("cpu_usage", "CPU Usage", "usage(%)"),])
# HostDataView

class ClientDataView(GraphDataView):
    text = "Client"
    metadata = PlotMetaData("time", [("gpu_usage", "GPU Usage", "usage(%)"),
                                     ("app_gpu_usage", "App GPU Usage", "usage(%)"),
                                     ("cpu_usage", "CPU Usage", "usage(%)"),
                                     ("app_cpu_usage", "App CPU Usage", "usage(%)")])

# ClientDataView

class FramesDataView(GraphDataView):
    text = "Frames"
    metadata = PlotMetaData("agent_time", [("size", "Size", "size(bytes)"),
                                           ("capture_duration", "Capture Duration", "duration(s)"),
                                           ("encode_duration", "Encode Duration", "duration(s)"),
                                           ("send_duration", "Send Duration", "duration(s)"),
                                           ("decode_duration", "Decode Duration", "duration(s)"),
                                           ("queue_size", "Queue Size", "frames(number)")])
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
