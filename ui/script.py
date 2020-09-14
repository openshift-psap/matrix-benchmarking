import os, time, datetime, atexit
import threading, subprocess
import types, importlib

import dash
from dash.dependencies import Output, Input, State
import dash_core_components as dcc
import dash_html_components as html

import utils.yaml

from . import InitialState, UIState
from . import feedback, graph, control

RESULTS_PATH = os.path.realpath(os.path.dirname(os.path.realpath(__file__)) + "/../results")

class ThreadInterrupt(Exception): pass

class Exec():
    def __init__(self, script, dry, mode):
        self.started = False
        self.interrupt = False
        self.mode = mode
        self.dry = dry
        self.script = script
        self.total_wait_time = 0
        self.py_fct_cache = {}

    def log(self, *args, ahead=False):
        if self.started and self.interrupt: raise ThreadInterrupt()

        msg = " ".join(map(str, args))
        if self.dry:
            if ahead:
                Script.messages.insert(0, msg)
            Script.messages.append(msg)

        else:
            print(datetime.datetime.now().strftime("%H:%M:%S"), msg)
            Script.messages.insert(0, msg)

    def _get_py_fct(self, name):
        try: return self.py_fct_cache[name]
        except KeyError: pass

        from . import machines
        state = types.SimpleNamespace()

        plugin_pkg_name = f"plugins.{self.mode}.scripting.{name}"
        mod = importlib.import_module(plugin_pkg_name)
        fct = getattr(mod, name)

        def wrap(args): fct(state, self, machines, args)

        self.py_fct_cache[name] = wrap, fct.__qualname__

        return wrap, f"{name}.{fct.__qualname__}"

    def _do_py_exec(self, name, args):
        fct, fct_name = self._get_py_fct(name)

        self.log(f"python-exec: {fct_name}({args})")

        fct(args) # fct will check for self.dry

    def execute(self, cmd):
        if self.interrupt: raise ThreadInterrupt()

        if cmd.startswith("/py/"):
            fct_name, _, args = cmd[5:].partition(" ")
            self._do_py_exec(fct_name, args)
        else:
            self.log("system-exec:", cmd)
            if self.dry: return

            p = subprocess.Popen(cmd.split(), close_fds=True)
            while True:
                if self.interrupt: p.terminate()

                try: p.wait(1)
                except subprocess.TimeoutExpired: pass
                else: break

        if self.interrupt: raise ThreadInterrupt()

    def apply_settings(self, driver, settings, force=False):
        self.log("apply_settings:", driver, ', '.join([f"{k}={v}" for k, v in settings.items()]))
        if self.dry and not force: return
        control.apply_settings(driver, settings)

    def request(self, msg, **kwargs):
        return control.request(msg, self.dry, self.log, **kwargs)

    def wait(self, nb_sec):
        self.log(f"wait {nb_sec} seconds")
        self.total_wait_time += nb_sec
        if self.dry: return
        for _ in range(nb_sec):
            if self.interrupt: raise ThreadInterrupt()
            time.sleep(1)

    def clear_feedback(self):
        self.log(f"clear feedback")
        if self.dry: return
        feedback.Feedback.clear()

    def append_feedback(self, msg):
        feedback_msg = (0, "script", msg)
        self.log(f"append to feedback:", ": ".join(feedback_msg[1:]))
        if self.dry: return
        feedback.Feedback.add_to_feedback(*feedback_msg)

    def clear_record(self):
        self.log(f"clear graphs")
        if self.dry: return
        UIState().DB.clear_graphs()

    def save_record(self, fname):
        if os.path.exists(fname):
            self.log(f"WARNING: record destination '{fname}' already exists ...")
            fname = fname + "_" + datetime.datetime.now().strftime("%y%m%d_%H%M%S")

        self.log(f"save record into {fname}")
        if self.dry:
            # make sure that we can create this file
            open(fname, "w")
            os.unlink(fname)
        else:
            UIState().DB.save_to_file(fname)

    def reset(self, driver_name=None, settings=None):
        self.log(f"reset benchmark")
        if self.dry: return
        control.reset_settings(driver_name, settings)


class Script():
    all_scripts = {}
    messages = []
    thr = None
    mode = None

    @staticmethod
    def load(mode, expe):
        script_cfg = os.path.realpath(os.path.dirname(os.path.realpath(__file__)) + "/../"
                                      + f"cfg/{mode}/benchmarks.yaml")
        Script.mode = mode
        Script.all_scripts.clear()

        all_yaml_desc = utils.yaml.load_all(script_cfg)

        for yaml_script_desc in all_yaml_desc:
            if not yaml_script_desc: continue
            if yaml_script_desc.get("disabled", False) is True: continue
            _engine = yaml_script_desc.get("_engine")

            plugins_pkg_name = f"plugins.{mode}.scripting.{_engine}"

            try:
                script_mod = importlib.import_module(plugins_pkg_name)
                script_mod.configure(expe)
                script_class = getattr(script_mod, _engine.capitalize())
                script_instance = script_class(yaml_script_desc)
            except Exception as e:
                print(f"ERROR: Cannot instantiate script plugin ({plugins_pkg_name}) ...", e)
                continue

            Script.all_scripts[script_instance.to_id()] = script_instance

    def __init__(self, yaml_desc):
        self.yaml_desc = yaml_desc

        self.name = yaml_desc["_name"]
        self.nb_agents = yaml_desc["_nb_agents"]

    def to_id(self):
        return self.name.lower().replace(" ", "-")

    def run(self, dry):
        exe = Exec(self, dry, Script.mode)
        def connected(): return UIState().DB.expe.agents_connected()
        if dry:
            exe.log(f"Running {self.name} (dry)")
            self.do_run(exe)
            if exe.total_wait_time != 0:
                exe.log(f"Estimated time: {exe.total_wait_time/60:.0f}min{exe.total_wait_time%60}s", ahead=True)
        elif Script.thr:
            exe.log("Failed, a script thread is already running ...")
        else:
            def thr_cleanup():
                if not Script.thr: return

                try:
                    exe.interrupt = True
                    Script.thr.join()
                except Exception as e:
                    print("ui.script.Script: failed to interrupt:", e)

            def run_thr(exe):
                Script.messages.clear()
                exe.log(f"Running {self.name}!")

                while self.nb_agents and len(connected()) != self.nb_agents:
                    if connected():
                        print(f"Agents connected: {','.join(connected())}")
                    print(f"Waiting to have {self.nb_agents} agents connected ...")
                    time.sleep(1)
                    if exe.interrupt: return

                exe.log(f"Agents connected: {', '.join(connected())}")
                self.started = True
                try: self.do_run(exe)
                except ThreadInterrupt: pass
                else: exe.log(f"Agents connected: {', '.join(connected())}")

                self.started = False

                if exe.interrupt: exe.log("INTERRUPTED")

                atexit.unregister(thr_cleanup)
                Script.thr = None

            Script.thr = threading.Thread(target=run_thr, args=(exe,))
            atexit.register(thr_cleanup)
            Script.thr.start()

            return Script.thr
