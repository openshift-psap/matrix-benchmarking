import time, math

from ui import graph, UIState
from plugins.adaptive.scripting import matrix as adaptive_matrix
from plugins.adaptive.scripting.matrix import Matrix

global running
running = False

class SpecfemMatrix():

    @staticmethod
    def add_custom_properties(yaml_desc, params):
        pass # nothing

    @staticmethod
    def get_path_properties(yaml_expe):
        return ["network", "platform"]

    @staticmethod
    def prepare_new_record(exe, context, settings_dict):
        global running
        if running: print("Already running ....")

        exe.reset(None, settings_dict)

        nproc = int(settings_dict["processes"])
        if int(math.pow(int(math.sqrt(nproc)), 2)) != nproc:
            print(f"WARNING: invalid 'processes' configuration (={nproc}) in {settings_dict}")
            exe.expe_cnt.errors += 1
            return

        if not exe.dry:
            running = True

        exe.apply_settings(context.params.driver, settings_dict)

        exe.clear_record()
        exe.clear_feedback()

    @staticmethod
    def wait_end_of_recording(exe, context):
        if exe.dry:
            print("Waiting for the end of the execution ... [dry]")
            return True

        exe.log("Waiting for the end of the execution ...")
        from utils.live import get_quit_signal

        i = 0
        while running:
            time.sleep(1)
            print(".", end="", flush=True)
            i += 1
            if get_quit_signal():
                raise KeyboardInterrupt()
        print()

        exe.log(f"Execution completed after {i} seconds (={int(i/60)}min).")

        for table_def, table_vals in UIState().DB.table_contents.items():
            if not table_def.table_name.endswith(".timing"):
                continue
            exe.log(f"Timing table has {len(table_vals)} records.")
            if len(table_vals) == 0:
                # 'timin' table empty ...
                exe.expe_cnt.errors += 1
                return False

            return True

        # 'timing' table not found ...
        exe.expe_cnt.errors += 1
        exe.log("Timing table missing :(")
        return False

def add_to_feedback_cb(ts, src, msg):
    global running
    if src == "agent" and "Specfem finished" in msg:
        print("\nFINISHED:", msg)
        running = False

def configure(expe):
    adaptive_matrix.configure(expe)

    adaptive_matrix.customized_matrix = SpecfemMatrix

    expe.new_feedback_cbs.append(add_to_feedback_cb)
