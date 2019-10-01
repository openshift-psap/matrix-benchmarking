import asyncio

measurements = None
loop = None
dead_measurements = None

def setup(_measurements, _dead_measurements):
    global measurements, dead_measurements
    measurements = _measurements
    dead_measurements = _dead_measurements


def _register_module(mod):
    measurements.append(mod)
    dead_measurements.append(measurements[-1]) # avoid smart_agent death message
    try:
        asyncio.get_event_loop().stop()
    except RuntimeError: pass # There is no current event loop in thread '...'.

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
