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
