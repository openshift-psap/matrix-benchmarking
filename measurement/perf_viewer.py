import json
import sys

import measurement
import measurement.perf_collect
import utils.live

class DummyLiveCollect(utils.live.LiveCollect):
    def connect(self, loop, process=None):
        self.alive = True
        pass

class Perf_Viewer(measurement.Measurement):
    feedback_for_ui = None

    def __init__(self, cfg, experiment, input_f=None):
        measurement.Measurement.__init__(self, experiment)
        self.experiment = experiment
        self.live = DummyLiveCollect()

        if input_f is None:
            try:
                self.input_f = open(sys.argv[2])
            except (IndexError, FileNotFoundError):
                raise IOError("Please launch the viewer with "+" ".join(sys.argv+["FILE.rec"]))
        else:
            self.input_f = input_f

        self.perf_collect = measurement.perf_collect.Perf_Collect({'machines':{}}, self.experiment)

    def setup(self):
        pass

    def start(self):
        parser = parse_rec_file(self.input_f)

        _, feedback_rows = next(parser)

        for entry in feedback_rows:
            self.experiment.new_feedback(*entry)

        print(len(feedback_rows), "feedback messages reloaded")

        if Perf_Viewer.feedback_for_ui is None:
            print("WARNING: feedback graph markers not shared with UI.")

        while True:
            _, _table_def = next(parser)
            if not _table_def: break

            _, table_rows= next(parser)
            _, feedback_rows = next(parser)

            # eg: table_def = '#host.mem|time;mem.free'
            mode = _table_def[1:].split(".")[0]
            table_def = _table_def.replace(f"#{mode}.", "#")

            table = measurement.perf_collect.Perf_Collect.do_create_table(self.experiment, table_def, mode)
            for row in table_rows:
                table.add(*row)

            if Perf_Viewer.feedback_for_ui is not None:
                Perf_Viewer.feedback_for_ui[table] = feedback_rows

            print(f"{table.table_name}: {len(table_rows)} rows reloaded.")

        print("Reloading completed.")
        self.input_f.close()

    def stop(self):
        pass

    def process_line(self, buf):
        pass

def parse_rec_file(input_f):
    yield "feedback_rows", json.loads(input_f.readline())

    while True:
        table_def = input_f.readline()
        if not table_def:
            break
        yield "table_def", table_def[:-1]
        yield "table_rows", json.loads(input_f.readline())
        yield "feedback_rows", json.loads(input_f.readline())

    yield "table_def", None
