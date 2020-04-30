import time

from ui import graph
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
        return []

    @staticmethod
    def prepare_new_record(exe, context, settings_dict):
        global running
        if running: print("Already running ....")

        exe.reset()
        running = True

        exe.apply_settings(context.params.driver, settings_dict)

        exe.clear_record()
        exe.clear_feedback()

    @staticmethod
    def wait_end_of_recording(exe, context):
        if exe.dry:
            print("Waiting for the end of the execution ... [dry]")
            return

        print("Waiting for the end of the execution ...")
        from utils.live import get_quit_signal

        i = 0
        while running:
            time.sleep(1)
            print(".", end="", flush=True)
            i += 1
            if get_quit_signal():
                raise KeyboardInterrupt()

        print(f"\nExecution completed after {i} seconds.")


def add_to_feedback_cb(ts, src, msg):
    global running
    if src == "agent" and msg.startswith("execution time"):
        running = False

def configure(expe):
    adaptive_matrix.configure(expe)

    adaptive_matrix.customized_matrix = SpecfemMatrix

    expe.new_feedback_cbs.append(add_to_feedback_cb)
