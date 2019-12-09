import datetime
import json
import statistics
from collections import defaultdict

import utils.yaml

from . import quality
from . import UIState

class DB():
    def __init__(self):
        self.expe = None
        self.quality = []
        self.tables_by_name = defaultdict(list)
        self.table_contents = {}
        self.quality_by_table = defaultdict(list)
        self.table_for_spec = {}

        self.pipeline_idx = 0
        self.pipelines = {} # pipeline -> id
        self.pipelines_reversed = {} # id -> pipeline

    def new_table(self, table):
        self.table_contents[table] = []

        self.tables_by_name[table.table_name].append(table)

    def new_table_row(self, table, row):
        self.table_contents[table].append(row)

    def save_to_file(self, filename):
        print("Saving into", filename)
        output = open(filename, "w")
        print(json.dumps(self.quality), file=output)

        for table in self.expe.tables.values():
            print(table.header(), file=output)
            print(json.dumps(self.table_contents[table]), file=output)
            print(json.dumps(self.quality_by_table[table]), file=output)

    def init_quality_from_viewer(self):
        import measurement.perf_viewer

        measurement.perf_viewer.Perf_Viewer.quality_for_ui = self.quality_by_table

    def clear_graphs(self):
        for content in self.table_contents.values():
            content[:] = []
        self.quality_by_table .clear()

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
    def per_sec_5(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 5)

    @staticmethod
    def per_sec_20(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 20)

    @staticmethod
    def per_sec_60(Y_lst, X_lst):
        return GraphFormat.per_sec_N(Y_lst, X_lst, 60)

    @staticmethod
    def key_frames_40(Y_lst, X_lst):
        return GraphFormat.key_frames_N(Y_lst, X_lst, 40)

    @staticmethod
    def key_frames_from_qual(Y_lst, X_lst):
        db = UIState().DB
        for ts, src, msg in db.quality:
            try: pos = msg.index("keyframe-period=")
            except ValueError: continue

            #msg: 'encoding: bitrate=10000;rate-control=vbr;keyframe-period=60;framerate=35

            keyframe_period = int(msg[pos+len("keyframe-period="):].partition(";")[0])

            break
        else: return None

        return GraphFormat.key_frames_N(Y_lst, X_lst, keyframe_period)

    @staticmethod
    def key_frames_N(Y_lst, X_lst, PERIOD):
        first_set = Y_lst[:PERIOD]
        first_kf_pos = first_set.index(max(first_set))

        return [elt if ((pos % PERIOD) == first_kf_pos) else 0
                for pos, elt in enumerate(Y_lst)]


    @staticmethod
    def as_key_frames_period(Y_lst, X_lst):
        return GraphFormat.as_key_frames(Y_lst, X_lst, period=True)

    @staticmethod
    def as_key_frames(Y_lst, X_lst=None, period=False):
        KEY_NORMAL_SIZE_RATIO = 33/100
        MIN_KEYFRAME_PERIOD = 11

        avg_frame_size = statistics.mean(Y_lst)
        max_frame_size = max(Y_lst)
        min_keyframe_size = avg_frame_size + (max_frame_size-avg_frame_size) * KEY_NORMAL_SIZE_RATIO

        keyframe_positions = []
        while True:
            max_size = max(Y_lst)
            max_pos = Y_lst.index(max_size)

            Y_lst[max_pos] = 0

            if max_size < min_keyframe_size:
                # not big enough for a keyframe --> done
                break

            too_close = False
            for kf_pos, kf_size in keyframe_positions:
                if abs(kf_pos - max_pos) < MIN_KEYFRAME_PERIOD:
                    # too close to previous KF
                    too_close = True
                    break

            if too_close: continue

            keyframe_positions.append([max_pos, max_size])


        new = []
        prev_pos = 0
        for pos, val in sorted(keyframe_positions):
            if period:
                if not new:
                    # skip the first one as it's partial
                    value = None
                    prev_pos = pos
                else:
                    kf_dist = pos - prev_pos
                    if kf_dist >= MIN_KEYFRAME_PERIOD:
                        prev_pos = pos
                    else:
                        print("ERROR, keyframe too close!", kf_dist) # should have been detected earlier on
                        # do not change the position of the last keyframe, we're to close
                        kf_dist = new[-1]

                    value = kf_dist
            else:
                value = val

            padding = value if period else 0
            new += [padding] * (pos-len(new)) + [value]

        last_val = None if period else 0

        new += [last_val] * (len(Y_lst)-len(new))

        return new


    @staticmethod
    def per_sec_N(Y_lst, X_lst, n):
        from collections import deque
        cache = deque()

        def time_length(_cache):
            l = _cache[-1][0] - _cache[0][0]
            return l.total_seconds()

        enough = False
        new = []
        for x, y in zip(X_lst, Y_lst):
            cache.append((x, y))
            while time_length(cache) >= n:
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
    def as_delta(Y_lst, X_lst):
        new = [(stop-start).total_seconds() for start, stop in zip (X_lst, X_lst[1:])]
        if new: new.append(new[-1]) # so that len(new) == len(Y_lst)

        return new

    @staticmethod
    def as_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t) for t in Y_lst]

    @staticmethod
    def as_us_timestamp(Y_lst, X_lst):
        return [datetime.datetime.fromtimestamp(t/1000000) for t in Y_lst]

    @staticmethod
    def get_setting_modifier(operation_name):
        OPERATIONS = {
            'inverted': lambda x: 1/float(x),
        }

        def modifier(table, X_lst, X_raw, X_idx):
            db = UIState().DB
            qual = iter(db.quality_by_table[table])
            try: current_qual = next(qual)
            except StopIteration: qual = None
            new = []
            last_value = 0
            name, *operations = operation_name.split(" | ")
            for x_raw in X_raw:
                while qual and current_qual[0][X_idx] == x_raw:
                    qual_msg = current_qual[1]
                    if qual_msg.startswith("!encoding:") and name in qual_msg:
                        params = qual_msg.partition("params:")[-1].split(';')
                        for param in params:
                            if param.startswith("gst.prop="): param = param.partition("=")[-1]
                            if not param.startswith(name): continue
                            last_value= int(param.split("=")[1])
                            for op in operations:
                                last_value = OPERATIONS[op](last_value)
                            new.append(last_value)
                            break
                    try: current_qual = next(qual)
                    except StopIteration: qual = None
                else:
                    new.append(last_value)
            return new
        return modifier

class DbTableForSpec():
    @staticmethod
    def get_table_for_spec(graph_spec):
        db = UIState().DB

        try: return db.table_for_spec[str(graph_spec.yaml_desc)]
        except KeyError: pass

        for table in db.tables_by_name[graph_spec.table]:
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

        idx = self.idx(field)

        values = [(row[idx]) for row in self.content]
        if not values: return []

        try:
            return list(field.modify(values, X))
        except Exception as e:
            print(f"Modifier '{field.modify.__name__}' failed, returning identity:", e)
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

        self.field_name, _, modif = field_modif.partition("|")
        self.field_name = self.field_name.strip()
        modif = modif.strip()

        self.label = label if has_label else self.field_name

        self.modify = lambda y,x:y # will be modified if necessary

        if self.field_name == "setting":
            self.modify = GraphFormat.get_setting_modifier(modif)
            return

        if modif:
            try:
                self.modify = getattr(GraphFormat, modif)
            except AttributeError:
                print(f"WARNING: modifier '{modif}' not found ... using identity")

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
