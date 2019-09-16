#!/bin/env python

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator
import matplotlib.pyplot as pyplot
import numpy
from scipy.spatial.distance import cdist
import yaml

class Plot(object):

    def __init__(self, x, y, title, y_label=None, x_label='time(s)'):
        self.x = [_x for _x, _y in zip(x, y) if _y is not None]

        self.rel_x = numpy.array(self.x) - self.x[0] if self.x else []
        self.y = [_y for _x, _y in zip(x, y) if _y is not None]

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

    def __init__(self, x_attr, x_label, y_attr):
        self.x_attr = x_attr
        self.x_label = x_label
        self.y_attr = y_attr

        self.plots = []
    #__init__

    def process_data(self, data):
        if self.plots:
            return self.plots

        try:
            dataset_length = data.length(self.x_attr)
        except KeyError as e:
            print("WARNING: {} is an invalid 'x' key ({})".format(self.x_attr, e))
            return []

        x_data = [data.get(self.x_attr, row) for row in range(dataset_length)]

        for field, title, label in self.y_attr:
            try:
                y_data = [data.get(field, row) for row in range(dataset_length)]
                self.plots.append(Plot(x_data, y_data, title, label, self.x_label))
            except Exception as e:
                print("WARNING: Failed to build plot '{} - {} | {}'".format(title, field, label))
                print(e)

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
        self.tooltips = {}
        self.plots = {}
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
                self.plots[a] = p
                a.set(title=p.title, ylabel=p.y_label)
                if i == nrows-1:
                    a.set_xlabel(p.x_label)

                a.grid(which='both', linestyle=":")
                a.get_xaxis().set_minor_locator(AutoMinorLocator())
                a.plot(p.rel_x, p.y, '.-', picker=5)

            canvas = FigureCanvas(self.graph)
            canvas.set_size_request(900, 700)
            canvas.mpl_connect('pick_event', self.update_tooltip)

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
            self.tooltips = {}
        self.set_label_placeholder("Loading...")
    # unmap_cb

    def update_tooltip(self, event):
        line = event.artist
        event_xy = (event.mouseevent.xdata, event.mouseevent.ydata)
        xydata = line.get_xydata()

        ### FIXME
        # Pick closest valid point from click event
        # https://codereview.stackexchange.com/questions/28207/finding-the-closest-point-to-a-list-of-points
        idx = cdist([event_xy], xydata).argmin()
        ###

        x, y = xydata[idx]
        axes = line.axes
        x_label = self.plots[axes].x_label
        y_label = self.plots[axes].y_label
        txt = f"Index: {idx}\nRelative {x_label}: {x:0.5f}\n{y_label}: {y:0.5f}"

        try:
            tooltip = self.tooltips[axes]
            tooltip.xy = x, y
            tooltip.set_text(txt)
        except KeyError:
            tooltip = axes.annotate(txt, xy = (x,y),
                                    textcoords = "offset points", xytext = (-20, 20),
                                    bbox = {"boxstyle" : "round,pad=0.5", "fc" : "aliceblue", "alpha" : 0.9},
                                    arrowprops = {"arrowstyle" : "-|>"})
            tooltip.set_visible(True)
            self.tooltips[axes] = tooltip

        event.canvas.draw()
    # update_tooltip

# GraphDataView

def get_data_views(filename):
    views_cfg = yaml.safe_load(open(filename))

    data_views = []
    for tab_title, content in views_cfg.items():
        if not "x" in content:
            print("WARNING: tab '{}' has no 'x' field. Skipping it.".format(tab_title))
            continue

        x_source, found, x_label = content["x"].partition(", ")

        y_attr = []
        for plot_title, y in content.items():
            if plot_title == "x": continue

            y_source, found, y_desc = y.partition(", ")
            y_attr.append((y_source, plot_title, y_desc))

        class YamlDataView(GraphDataView):
            text = tab_title
            metadata = PlotMetaData(x_source, x_label, y_attr)

        data_views.append(YamlDataView)

    return data_views

class ExperimentDataView(Gtk.Grid, DataView):
    text = "Experiment"

    def __init__(self, data):
        DataView.__init__(self, data)
        Gtk.Grid.__init__(self,
                          border_width=10,
                          column_homogeneous=True,
                          column_spacing=10,
                          row_spacing=10)

        for i in range(2):
            self.insert_column(i)

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
