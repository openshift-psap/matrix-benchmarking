
class Measurement:
    """This class represent a measurement
    The purpose is to define the steps of the measurement.
    A measurement can be for instance how much CPU or memory is
    consumed.
    """
    def __init__(self, **kargs):
        """Initialization and possible initial base checks.
        If you need more expensive setup you probably should write it
        in setup() so to allow user to have a faster feedback before
        leaving the keyboard"""
        self.experiment = kargs['experiment']
    def setup(self):
        """Setup the measurement
        In this step you should launch any tool needed (like a CPU
        monitor) or save any measurement (like disk space)."""
        pass
    def start(self):
        """Start the measurement.
        start and stop are separate to allow to quickly start and
        stop all measurement.
        Do not do too expensive operation"""
        pass
    def stop(self):
        """Stop the measurement.
        See start"""
        pass
    def collect(self):
        """Collect the measurement.
        For instance get logs and parse them.
        Should store the results on a table."""
        pass
