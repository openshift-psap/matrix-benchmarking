import asyncio

measurements = None
loop = None
dead_measurements = None
force_recheck = None

def setup(_measurements, _dead_measurements, _force_recheck):
    global measurements, dead_measurements, force_recheck
    measurements = _measurements
    dead_measurements = _dead_measurements
    force_recheck = _force_recheck

def _register_module(mod):
    measurements.append(mod)
    dead_measurements.append(measurements[-1]) # avoid local_agent death message
    force_recheck.append(True)

def attach_to_pid(expe, mode, pid):
    from measurement import pidstat

    _register_module(pidstat.PidStat(dict(pid=pid, mode=mode), expe))

def load_record_file(expe, filename):
    from measurement import perf_viewer

    mod = perf_viewer.Perf_Viewer({}, expe, open(filename))
    mod.setup()
    mod.start()
    mod.stop()


def detach_module(mod):
    measurements.remove(mod)

    try: dead_measurements.remove(mod)
    except ValueError: pass # the module wasn't dead
