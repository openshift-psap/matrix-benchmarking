#!/bin/env python

import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

import sqlite3 as sqlite

from data import ExperimentData
from dataview import ExperimentDataView, FramesDataView, ClientDataView, \
                     HostDataView, GuestDataView

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
        theme = Gtk.IconTheme.get_default()
        theme.append_search_path("./icons")
        self.set_icon_name("spice")
        self.stack = None

        self.set_default_size(800, 600)

        # Custom title bar
        self.header = Gtk.HeaderBar()
        self.header.set_title("SPICE Streaming Stats Viewer")
        self.header.set_show_close_button(True)

        # Headerbar buttons
        self.header.pack_start(self.create_button("new", self.new_button_clicked))
        self.header.pack_start(self.create_button("open", self.open_button_clicked))

        # headerbar custom middle widget
        self.set_titlebar(self.header)

        self.add(Gtk.Image.new_from_file("icons/spice.png"))
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
        self.remove(self.get_child())
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
        GLib.set_prgname("Streaming stats")
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
