#!/bin/env python

import os
import traceback
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gio, Gtk

import sqlite3 as sqlite
import psycopg2

if __package__ is None:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from utils import yaml
else:
    from ..utils import yaml

from data import ExperimentData
from dataview import ExperimentDataView, FramesDataView, ClientDataView, \
                     HostDataView, GuestDataView, GraphDataView

class ExperimentView(Gtk.Notebook):

    def __init__(self, data):
        Gtk.Notebook.__init__(self, scrollable=True)
        self.append_page(ExperimentDataView, data)
        self.append_page(FramesDataView, data.frames)
        self.append_page(ClientDataView, data.client_stats)
        self.append_page(HostDataView, data.host_stats)
        self.append_page(GuestDataView, data.guest_stats)
        self.n_pages = self.get_n_pages()

        button = Gtk.Button(image=Gtk.Image.new_from_icon_name("tab-new-symbolic", Gtk.IconSize.BUTTON),
                            always_show_image=True,
                            tooltip_text="Custom tab")
        button.connect("clicked", self.new_tab_clicked)
        button.show()
        self.set_action_widget(button, Gtk.PackType.END)

        self.custom_tabs = []
        self.show()
    # __init__

    def append_page(self, type, data, tab_widget=None):
        if not tab_widget:
            tab_widget = Gtk.Label(label=type.text)

        return Gtk.Notebook.append_page(self, type(data), tab_widget)
    # append_page

    def new_tab_clicked(self, button):
        box = Gtk.Box(spacing=4, homogeneous=False)
        box.pack_start(Gtk.Label(label="Custom tab %d" % len(self.custom_tabs)), True, True, 0)
        close_button = Gtk.Button(image=Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON),
                                  always_show_image=True,
                                  relief=Gtk.ReliefStyle.NONE,
                                  tooltip_text="Close tab",
                                  focus_on_click=False)
        close_button.connect("clicked", self.close_tab_clicked)
        box.pack_end(close_button, False, True, 0)
        box.show_all()

        self.custom_tabs.append(close_button)
        self.set_current_page(self.append_page(GraphDataView, None, box))
    # new_tab_clicked

    def close_tab_clicked(self, button):
        idx = self.custom_tabs.index(button)
        self.remove_page(idx + self.n_pages)
        self.custom_tabs.pop(idx)
    # close_tab_clicked
# ExperimentView

class ExperimentsView(Gtk.Box):

    def __init__(self, db_path, remote_db_cfg):
        Gtk.Box.__init__(self, spacing=4,
                        homogeneous=False,
                        border_width=10)

        if db_path == '::remote':
            cfg = remote_db_cfg
            database = cfg.get('database', cfg['user'])
            self.db = psycopg2.connect(user = cfg['user'],
                                   password = cfg['password'],
                                   host = cfg['host'],
                                   port = cfg.get('port', '5432'),
                                   database = database)
            self.name = db_path
        else:
            self.db = sqlite.connect(db_path)
            self.name = os.path.split(db_path)[-1]

        self.stack = Gtk.Stack()
        switcher = Gtk.StackSidebar(stack=self.stack)

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
    # get_name
#ExperimentsView

class MainWindow(Gtk.ApplicationWindow):

    def __init__(self, files):
        Gtk.IconTheme.get_default().append_search_path("./icons")
        Gtk.ApplicationWindow.__init__(self,
                                       default_width=1024,
                                       default_height=768,
                                       icon_name="spice")

        self.stack = None

        # Custom title bar
        self.header = Gtk.HeaderBar(title="SPICE Streaming Stats Viewer",
                                    show_close_button=True)
        self.header.pack_start(self.create_button("new", self.new_button_clicked))
        self.header.pack_start(self.create_button("open", self.open_button_clicked))
        cfg = yaml.load_multiple("benchmark.yaml", "secure.yaml")
        self.remote_db_cfg = yaml.subyaml(cfg, 'databases/remote')
        if self.remote_db_cfg:
            self.header.pack_start(self.create_database_button())

        # headerbar custom middle widget
        self.set_titlebar(self.header)

        self.add(Gtk.Image.new_from_file("icons/spice.png"))
        for f in files:
            self.load_experiments(f)
    # __init__

    def create_button(self, action_name, cb):
        button = Gtk.Button(image=Gtk.Image.new_from_icon_name("document-%s-symbolic" % action_name, Gtk.IconSize.BUTTON),
                            always_show_image=True,
                            tooltip_text="%s experiment" % action_name.capitalize())
        button.connect("clicked", cb)
        button.show()
        return button
    # create_button

    def create_database_button(self):
        button = Gtk.Button(image=Gtk.Image.new_from_icon_name("network-wired-symbolic", Gtk.IconSize.BUTTON),
                            always_show_image=True,
                            tooltip_text="open remote experiments")
        button.connect("clicked", self.database_button_clicked)
        button.show()
        return button
    # create_button2

    def ensure_stack(self):
        if self.stack is not None:
            return

        self.stack = Gtk.Stack()
        self.remove(self.get_child())
        self.add(self.stack)
        self.stack.show()

        s = Gtk.StackSwitcher(stack=self.stack)
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

    def experiments_is_loaded(self, path):
        if self.stack is None:
            return False

        if self.stack.get_child_by_name(path) is None:
            return False

        print('%s is already loaded' % path)
        return True
    # experiments_loaded

    def load_experiments(self, path):
        if self.experiments_is_loaded(path):
            experiments = self.stack.get_child_by_name(path)
        else:
            try:
                experiments = ExperimentsView(path, self.remote_db_cfg)
            except Exception as e:
                print(traceback.format_exc())
                dialog = Gtk.MessageDialog(text=str(e).capitalize(),
                                           transient_for=self,
                                           buttons=Gtk.ButtonsType.OK,
                                           message_type=Gtk.MessageType.ERROR)

                dialog.run()
                dialog.destroy()
                return

            self.ensure_stack()
            self.stack.add_titled(experiments, path, experiments.get_name())
            self.stack.show_all()

        self.stack.set_visible_child(experiments)
    # load_experiments

    def open_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog(title="Load database file",
                                       transient_for=self)
        dialog.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        ret = dialog.run()
        path = None
        if ret == Gtk.ResponseType.OK:
            path = dialog.get_filename()

        dialog.destroy()

        if path:
            self.load_experiments(path)
    # open_button_clicked

    def database_button_clicked(self, button):
        self.load_experiments('::remote')
    # database_button_clicked

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
