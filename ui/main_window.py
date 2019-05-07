#!/bin/env python

import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as pyplot
import numpy

import sqlite3 as sqlite

from data import ExperimentData

class DataView(object):
    def __init__(self, data):
        self.data = data
    # __init__
#DataView

class Plot(object):
    def __init__(self, x, y, label, y_label=None, x_label='time(s)'):
        self.x = x
        self.y = y
        if y_label is not None:
            label = '%s (%s / %s)' % (label, y_label, x_label)
        self.label = label
    # __init__
# Plot

class GraphDataView(Gtk.ScrolledWindow, DataView):
    def __init__(self, data, plots=[]):
        Gtk.ScrolledWindow.__init__(self)
        DataView.__init__(self, data)

        if not data:
            self.add(Gtk.Label("No data provided"))
            return

        graph, axes = pyplot.subplots(nrows=len(plots))
        for i in xrange(len(plots)):
            a = axes[i]
            p = plots[i]
            a.set_title(p.label)
            a.grid()
            a.plot(p.x, p.y, '.-')

        canvas = FigureCanvas(graph)
        canvas.set_size_request(800, 600)
        self.add_with_viewport(canvas)
        self.show()
    # __init__
#GraphDataView

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
            gpu_mem.append(d.gpu_memory or 0)
            gpu_usage.append(d.gpu_usage or 0)
            encode_usage.append(d.encode_usage or 0)
            decode_usage.append(d.decode_usage or 0)

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
            cpu_usage.append(d.cpu_usage or 0)

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
            gpu_usage.append(d.gpu_usage or 0)
            app_gpu_usage.append(d.app_gpu_usage or 0)
            cpu_usage.append(d.cpu_usage or 0)
            app_cpu_usage.append(d.app_cpu_usage or 0)

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
            size.append(d.size or 0)
            mm_time.append(d.mm_time)
            capture_duration.append(d.capture_duration or 0)
            encode_duration.append(d.encode_duration or 0)
            send_duration.append(d.send_duration or 0)
            client_time.append(d.client_time)
            decode_duration.append(d.decode_duration or 0)
            queue_size.append(d.queue_size or 0)

        plots = [Plot(agent_time, size, "Size", "size(bytes)"),
                 Plot(agent_time, capture_duration, "Capture Duration", "duration(s)"),
                 Plot(agent_time, encode_duration, "Encode Duration", "duration(s)"),
                 Plot(agent_time, send_duration, "Send Duration", "duration(s)"),
                 Plot(agent_time, decode_duration, "Decode Duration", "duration(s)"),
                 Plot(agent_time, queue_size, "Queue Size", "frames(number)")]

        GraphDataView.__init__(self, data, plots)
    # __init__

# FramesView

class ExperimentDataView(Gtk.Grid, DataView):
    text = "Experiment"
    def __init__(self, data):
        Gtk.Grid.__init__(self)
        DataView.__init__(self, data)

        self.insert_column(0)
        self.insert_column(1)
        self.insert_column(2)
        self.set_border_width(10)
        self.set_column_homogeneous(True)
        self.set_column_spacing(10)
        self.set_row_spacing(10)

        row = 0
        for key, val in data:
            self.display_data(key, val, row)
            row += 1
        self.show_all()
    # __init__

    def display_data(self, text, value, row):
        self.insert_row(row)
        w = Gtk.Label("")
        w.set_xalign(1.0)
        w.set_markup("<b>%s:</b>" % text.capitalize())
        self.attach(w, 0, row, 1, 1)

        w = Gtk.Label("")
        w.set_xalign(0.0)
        if not value:
            value = "<i>not provided</i>"

        w.set_markup("%s" % value)
        self.attach(w, 1, row, 2, 1)
    # display_data
# ExperimentDataView

class ExperimentView(Gtk.Notebook):
    def __init__(self, data):
        Gtk.Notebook.__init__(self)
        self.append_page(ExperimentDataView, data)
        self.append_page(FramesDataView, data.frames)
        self.append_page(ClientDataView, data.client_stats)
        self.append_page(HostDataView, data.host_stats)
        self.append_page(GuestDataView, data.guest_stats)
        self.show()
    # __init__

    def append_page(self, type, data):
        Gtk.Notebook.append_page(self, type(data), Gtk.Label(type.text))
    # add_graph
# ExperimentView

class ExperimentsView(Gtk.Box):

    def __init__(self, db_path):
        Gtk.Box.__init__(self, Gtk.Orientation.VERTICAL, 4)
        self.set_homogeneous(False)
        self.set_border_width(10)
        self.db = sqlite.connect(db_path)
        self.name = os.path.split(db_path)[-1]

        switcher = Gtk.StackSidebar()
        self.stack = Gtk.Stack()
        switcher.set_stack(self.stack)

        for experiment in ExperimentData.load(self.db):
            self.load_experiment(experiment)

        self.pack_start(switcher, False, True, 0)
        self.pack_start(self.stack, True, True, 0)
        self.stack.show_all()
        switcher.show_all()
    # __init__

    def load_experiment(self, experiment):
        view = ExperimentView(experiment)
        self.stack.add_titled(view, experiment.uuid, str(experiment.id))
    # load_experiment

    def close(self):
        print("disconnect database")
        self.db.close()
    # close

    def get_name(self):
        return self.name
    # get_experiment
#ExperimentsView

class MainWindow(Gtk.ApplicationWindow):

    def __init__(self, files):
        Gtk.ApplicationWindow.__init__(self)
        self.stack = None

        self.set_default_size(800, 600)

        # Custom title bar
        self.header = Gtk.HeaderBar()
        self.header.set_title("Smart Streaming Stats Viewer")
        self.header.set_show_close_button(True)

        # Headerbar buttons
        self.header.pack_start(self.create_button("new", self.new_button_clicked))
        self.header.pack_start(self.create_button("open", self.open_button_clicked))

        # headerbar custom middle widget
        self.set_titlebar(self.header)

        for f in files:
            self.load_experiments(f)
    # __init__

    def create_button(self, action_name, cb):
        button = Gtk.Button()
        button.set_image(Gtk.Image.new_from_icon_name("document-%s-symbolic" % action_name, Gtk.IconSize.BUTTON))
        button.set_always_show_image(True)
        button.set_tooltip_text("%s experiment" % action_name.capitalize())
        button.connect("clicked", cb)
        button.show()
        return button
    # create_button

    def ensure_stack(self):
        if self.stack is not None:
            return

        self.stack = Gtk.Stack()
        self.add(self.stack)
        self.stack.show()

        s = Gtk.StackSwitcher()
        s.set_stack(self.stack)
        s.show()

        self.header.set_custom_title(s)
        self.header.show()
    # ensure_stack

    def new_experiment(self):
        pass
    # new_experiment

    def new_button_clicked(self, button):
        self.new_experiment()
    # new_button_clicked

    def load_experiments(self, path):
        self.ensure_stack()
        experiments = self.stack.get_child_by_name(path)
        if experiments is None:
            experiments = ExperimentsView(path)
            self.stack.add_titled(experiments, path, experiments.get_name())
            self.stack.show_all()
        else:
            print('%s is already loaded' % path)

        self.stack.set_visible_child(experiments)
    # load_experiments

    def open_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog()
        dialog.set_title("Load database file")
        dialog.set_transient_for(self)
        dialog.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        ret = dialog.run()
        if ret == Gtk.ResponseType.OK:
            self.load_experiments(dialog.get_filename())

        dialog.destroy()
    # open_button_clicked

    def close_experiments(self, experiment):
        experiment.close()
        self.stack.remove(experiment)
    # close_experiments

    def close_all_experiments(self):
        if self.stack is None:
            return

        for experiment in self.stack.get_children():
            self.close_experiments(experiment)
    # close_all_experiments

# MainWindow

class StatsApp(Gtk.Application):

    def __init__(self):
        Gtk.Application.__init__(self,
                                 application_id='org.spice-space.streaming-stats',
                                 flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
    #__init__

    def do_shutdown(self):
        if self.window:
            self.window.close_all_experiments()
        Gtk.Application.do_shutdown(self)
    # do_shutdown

    def do_activate(self):
        self.window = MainWindow(self.args[1:])
        self.add_window(self.window)
        self.window.show_all()
    # do_activate

    def do_command_line(self, command_line):
        self.args = command_line.get_arguments()
        self.activate()
        return 0
    # do_command_line
# StatsApp

if __name__ == "__main__":
    import sys
    app = StatsApp()
    app.run(sys.argv)
