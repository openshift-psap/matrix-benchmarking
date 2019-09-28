expe = None
measurements = None
loop = None
dead_measurements = None

def setup(_loop, _expe, _measurements, _dead_measurements):
    global expe, measurements, loop, dead_measurements
    loop = _loop
    expe = _expe
    measurements = _measurements
    dead_measurements = _dead_measurements

def attach_to_pid(mode, pid):
    assert expe is not None

    from measurement import pidstat

    measurements.append(pidstat.PidStat(dict(pid=pid, mode=mode), expe))
    dead_measurements.append(measurements[-1]) # avoid smart_agent death message
    loop.stop()
