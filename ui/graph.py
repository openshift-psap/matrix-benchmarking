import datetime
import json
import statistics
from collections import defaultdict
import importlib

import utils.yaml

from . import feedback
from . import UIState

plugin = None

def configure(mode):
    global plugin
    plugin_pkg_name = f"plugins.{mode}.graph"
    try: plugin = importlib.import_module(plugin_pkg_name)
    except ModuleNotFoundError:
        return
    except Exception as e:
        print(f"ERROR: Cannot load control plugin package ({plugin_pkg_name}) ...")
        raise e
    try:
        dataview_yaml = utils.yaml.load_multiple(f"cfg/{mode}/dataview.yaml")
        return DataviewCfg(dataview_yaml)
    except FileNotFoundError:
        return


class DB():
    def __init__(self):
        self.expe = None
        self.feedback = []
        self.tables_by_name = defaultdict(list)
        self.table_contents = {}
        self.feedback_by_table = defaultdict(list)
        self.table_for_spec = {}
        self.seconds_to_keep = None # None for 'keep all', n to keep only n seconds

        feedback.plugin.init_db(self)

    def new_table(self, table):
        self.table_contents[table] = []

        self.tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        self.table_contents[table].append(row)

    def save_to_file(self, filename):
        print("Saving into", filename)
        with open(filename, "w") as output:
            print(json.dumps(self.feedback), file=output)

            for table in self.expe.tables.values():
                print(f"- {table.table_name}: {len(self.table_contents[table])} rows")
                print(table.header(), file=output)
                print(json.dumps(self.table_contents[table]), file=output)
                print(json.dumps(self.feedback_by_table[table]), file=output)

    def init_feedback_from_viewer(self):
        import measurement.perf_viewer

        measurement.perf_viewer.Perf_Viewer.feedback_for_ui = self.feedback_by_table

    def clear_graphs(self):
        for content in self.table_contents.values():
            content[:] = []
        self.feedback_by_table .clear()

class GraphFormat():
    @staticmethod
    def as_KB_to_GB(Y_lst, X_lst):
        return [v/1000/1000 for v in Y_lst]

    @staticmethod
    def as_B_to_KB(Y_lst, X_lst):
        return [v/1000 for v in Y_lst]

    @staticmethod
    def as_s_to_ms(Y_lst, X_lst):
        return [v*1000 for v in Y_lst]

    @staticmethod
    def as_us_to_ms(Y_lst, X_lst):
        return [v/1000 for v in Y_lst]

    @staticmethod
    def inverted(Y_lst, X_lst):
        return [1/y for y in Y_lst]

    @staticmethod
    def as_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t) for t in Y_lst]

    @staticmethod
    def as_us_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t/1000000) for t in Y_lst]

class DbTableForSpec():
    @staticmethod
    def get_table_for_spec(graph_spec):
        db = UIState().DB

        try: return db.table_for_spec[str(graph_spec.yaml_desc)]
        except KeyError: pass

        if graph_spec.table in db.tables_by_name: # it's a default dict, so no KeyError
            tables = db.tables_by_name[graph_spec.table]
        elif graph_spec.table.startswith("?."):
            name = graph_spec.table[1:] # ?.name --> .name
            for tbl_name, tbl in db.tables_by_name.items():
                if not tbl_name.endswith(name): continue
                tables = tbl
                break
            else:
                tables = []
        else:
            tables = []

        for table in tables:
            for ax in graph_spec.all_axis:
                if ax.field_name == "setting": continue
                if ax.field_name not in table.fields:
                    break
            else: # didn't break, all the fields are present
                break
        else: # didn't break, table not found
            table = None
            table_for_spec = None

        if table:
            table_for_spec = DbTableForSpec(table, graph_spec)
            db.table_for_spec[str(graph_spec.yaml_desc)] = table_for_spec

        return table_for_spec

    def __init__(self, table, graph_spec):
        self.table = table
        self.graph_spec = graph_spec

        self.content = UIState().DB.table_contents[table]

    def idx(self, field):
        return self.table.fields.index(field.field_name)

    def get(self, field, X):
        if field.field_name == "setting":
            return field.modify(self.table, X, self.get_raw_x(), self.idx(self.graph_spec.x))

        try:
            idx = self.idx(field)
        except ValueError:
            print(f"ERROR: could not find field '{field.field_name}' to plot '{field.label}' ...")
            return []

        try:
            values = [(row[idx]) for row in self.content]
        except IndexError:
            print(f"ERROR: IndexError while trying to plot '{field.field_name}' ({field.label.strip()}) ...")
            print(f"INFO: the table certainly doesn't always have at least {idx+1} columns ...")
            return []

        if not values: return []

        try:
            return list(field.modify(values, X))
        except Exception as e:
            print(f"Modifier '{field.modify.__name__}' failed, returning identity:", e)
            import traceback
            traceback.print_exc()
            return values

    def get_raw_x(self):
        idx = self.idx(self.graph_spec.x)

        return [row[idx] for row in self.content]

    def get_first_raw_x(self):
        return self.content[0][self.idx(self.graph_spec.x)]

    def get_x(self):
        return self.get(self.graph_spec.x, None)

    def get_all_y(self, X):
        for y_field in self.graph_spec.all_y_axis:
            yield y_field, self.get(y_field, X)


class FieldSpec():
    def __init__(self, yaml_desc):
        field_modif, has_label, label = yaml_desc.partition(">")

        self.field_name, *modif = field_modif.split("|")
        self.field_name = self.field_name.strip()

        self.label = label if has_label else self.field_name

        self.modify = lambda y,x:y # will be modified if necessary

        if self.field_name == "setting":
            self.modify = plugin.GraphFormat.get_setting_modifier(modif)
            return

        if not modif: return

        try: plugin_graph_format = plugin.GraphFormat
        except AttributeError:
            plugin_graph_format = False

        modifiers = []
        try:
            for mod in modif:
                name = mod.strip()
                if plugin_graph_format and hasattr(plugin_graph_format, name):
                    fmt = getattr(plugin.GraphFormat, name)
                else:
                    fmt = getattr(GraphFormat, name)
                modifiers.append(fmt)
        except AttributeError:
            print(f"WARNING: modifier '{mod}' not found ... using identity")
        else:
            def apply_modifiers(y, x):
                for mod_fct in modifiers:
                    y = mod_fct(y, x)
                return y

            self.modify = apply_modifiers


class GraphSpec():
    def __init__(self, graph_tab, graph_name, yaml_desc):
        self.graph_tab = graph_tab
        self.graph_name = graph_name
        self.yaml_desc = yaml_desc
        self.table = yaml_desc["table"]
        self.mode = yaml_desc.get("mode", "lines")

        self.x = FieldSpec(yaml_desc["x"])

        self.all_y_axis = []
        for ax in [k for k in yaml_desc.keys()
                   if k.startswith("y") and (not k[1:] or k[1:].isnumeric())]:
            try:
                self.all_y_axis.append(FieldSpec(yaml_desc[ax]))
            except KeyError: pass
        self.all_axis = [self.x] + self.all_y_axis

        try:
            self.y_max = self.yaml_desc["y_max"]
        except KeyError: pass

        try:
            self.y_title = self.yaml_desc["y_title"]
        except KeyError: pass

    def get_spec(self, name):
        return self.yaml_desc[name]

    def to_id(self):
        return self.graph_tab.to_id() + "-" + self.graph_name.lower().replace(" ", "-")


class GraphTabContent():
    def __init__(self, tab_name, yaml_desc):
        self.tab_name = tab_name
        self.yaml_desc = yaml_desc

        self.graphs = [GraphSpec(self, graph_name, graph_spec)
                       for graph_name, graph_spec in self.yaml_desc.items()
                       if not graph_spec.get("_disabled")]

    def to_id(self):
        return self.tab_name.lower().replace(" ", "-")

class DataviewCfg():
    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc

        self.tabs = [GraphTabContent(tab_name, graph_tab_content)
                     for tab_name, graph_tab_content in self.yaml_desc.items()]
