# power_sink.py
from pythonfmu.fmi2slave import Fmi2Slave

class PowerSink(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.power_in = 0.0
        self.energy = 0.0

    def do_step(self, current_time, step_size):
        self.energy += self.power_in * step_size
        return True

    def get_real(self, vr):
        if vr == 0:
            return self.energy
        return 0.0

    def set_real(self, vr, value):
        if vr == 1:
            self.power_in = value
