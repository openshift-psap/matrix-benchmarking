import datetime
import json
import statistics
from collections import defaultdict

import utils.yaml

from . import quality

class DB():
    expe = None

    tables_by_name = defaultdict(list)
    table_definitions = {}
    table_contents = {}
    quality_by_table = defaultdict(list)

    @staticmethod
    def save_to_file(filename):
        print("Saving into", filename)
        output = open(filename, "w")
        print(json.dumps(quality.Quality.quality), file=output)

        for table in DB.expe.tables:
            print(table.header(), file=output)
            print(json.dumps(DB.table_contents[table]), file=output)
            print(json.dumps(DB.quality_by_table[table]), file=output)

    @staticmethod
    def init_quality_from_viewer():
        import measurement.perf_viewer

        measurement.perf_viewer.Perf_Viewer.quality_for_ui = DB.quality_by_table

    @staticmethod
    def clear_graphs():
        for content in DB.table_contents.values():
            content[:] = []
        DB.quality_by_table .clear()

class GraphFormat():
    @staticmethod
    def as_B_to_GB(Y_lst, X_lst):
        return [v/1000/1000 for v in Y_lst]

    @staticmethod
    def per_sec_5(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 5)

    @staticmethod
    def per_sec_20(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 20)

    @staticmethod
    def per_sec_60(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 60)

    @staticmethod
    def per_sec_N(Y_lst, X_lst, n):
        from collections import deque
        cache = deque()

        def time_length(_cache):
            l = _cache[-1][0] - _cache[0][0]
            return l.seconds

        enough = False
        new = []
        for x, y in zip(X_lst, Y_lst):
            cache.append((x, y))
            while time_length(cache) > n:
                cache.popleft()
                enough = True

            if not enough:
                new.append(None)
            else:
                new.append(sum([y for x,y in cache]) / n)

        return new

    @staticmethod
    def as_it_is(Y_lst, X_lst):
        print(Y_lst)
        return Y_lst

    @staticmethod
    def as_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t) for t in Y_lst]

    @staticmethod
    def as_us_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t/1000000) for t in Y_lst]

class DbTableForSpec():
    table_for_spec = {}

    @staticmethod
    def get_table_for_spec(graph_spec):
        try: return DbTableForSpec.table_for_spec[str(graph_spec.yaml_desc)]
        except KeyError: pass

        for table in DB.tables_by_name[graph_spec.table]:
            for ax in graph_spec.all_axis:
                if ax.field_name not in table.fields:
                    break
            else: # didn't break, all the fields are present
                break
        else: # didn't break, table not found
            print(f"WARNING: No table found for {graph_spec.yaml_desc}")
            table = None
            table_for_spec = None

        if table:
            table_for_spec = DbTableForSpec(table, graph_spec)

        DbTableForSpec.table_for_spec[str(graph_spec.yaml_desc)] = table_for_spec

        return table_for_spec

    def __init__(self, table, graph_spec):
        self.table = table
        self.graph_spec = graph_spec

        self.content = DB.table_contents[table]

    def idx(self, field):
        return self.table.fields.index(field.field_name)

    def get(self, field, X):
        idx = self.idx(field)

        values = [(row[idx]) for row in self.content]
        try:
            return list(field.modify(values, X))
        except Exception as e:
            print(e)

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

        self.field_name, _, modif = field_modif.partition("|")
        self.field_name = self.field_name.strip()

        self.label = label if has_label else self.field_name

        try:
            self.modify = getattr(GraphFormat, modif.strip())
        except AttributeError:
            self.modify = lambda y,x:y

class GraphSpec():
    def __init__(self, graph_tab, graph_name, yaml_desc):
        self.graph_tab = graph_tab
        self.graph_name = graph_name
        self.yaml_desc = yaml_desc
        self.table = yaml_desc["table"]

        self.x = FieldSpec(yaml_desc["x"])

        self.all_y_axis = []
        for ax in "y", "y2", "y3", "y4":
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
