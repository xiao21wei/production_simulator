import math
import time


class SimulationClock:
    """Map simulation time to wall-clock time using a speed multiplier."""

    def __init__(
        self,
        real_time_step=1.0,
        speed=10.0,
        realtime=True,
        monotonic_fn=None,
        sleep_fn=None,
    ):
        self._real_time_step = self._validate_positive(
            "real_time_step", real_time_step
        )
        self._speed = self._validate_positive("speed", speed)
        self._realtime = bool(realtime)
        self._monotonic = monotonic_fn or time.monotonic
        self._sleep = sleep_fn or time.sleep
        self._anchor_wall_time = None
        self._anchor_simulation_time = None
        self.current_simulation_time = 0.0
        self.is_running = False
        self._pause_event = None

    @staticmethod
    def _validate_positive(name, value):
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive finite number.")
        return value

    @property
    def real_time_step(self):
        """Wall-clock seconds represented by one simulation time step."""
        return self._real_time_step

    @real_time_step.setter
    def real_time_step(self, value):
        self._real_time_step = self._validate_positive("real_time_step", value)

    @property
    def speed(self):
        """Simulation time units advanced per wall-clock second."""
        return self._speed

    @speed.setter
    def speed(self, value):
        self._speed = self._validate_positive("speed", value)
        if self.is_running:
            self._rebase()

    @property
    def simulation_time_step(self):
        """Simulation time advanced during one configured real-time step."""
        return self.real_time_step * self.speed

    @property
    def realtime(self):
        return self._realtime

    @realtime.setter
    def realtime(self, value):
        self._realtime = bool(value)
        if self.is_running:
            self._rebase()

    def start(self, simulation_time=0.0):
        """Start or restart the wall-clock anchor."""
        self.current_simulation_time = float(simulation_time)
        self.is_running = True
        self._rebase()

    def set_pause_event(self, pause_event):
        self._pause_event = pause_event

    def pause(self):
        if self._pause_event is not None:
            self._pause_event.clear()
        self._rebase()

    def resume(self):
        if self._pause_event is not None:
            self._pause_event.set()
        self._rebase()

    def stop(self):
        self.is_running = False
        self._anchor_wall_time = None
        self._anchor_simulation_time = None

    def wait_until(self, simulation_timestamp):
        """Block until a simulation timestamp is reached."""
        simulation_timestamp = float(simulation_timestamp)
        if simulation_timestamp < self.current_simulation_time:
            raise ValueError(
                "simulation_timestamp cannot be earlier than the current "
                "simulation time."
            )

        while (
            self._realtime
            and simulation_timestamp > self.current_simulation_time
        ):
            if (
                self._pause_event is not None
                and not self._pause_event.is_set()
            ):
                self._pause_event.wait()
                self._rebase()
                continue

            target_wall_time = self._anchor_wall_time + (
                simulation_timestamp - self._anchor_simulation_time
            ) / self.speed
            remaining = target_wall_time - self._monotonic()
            if remaining > 0:
                sleep_time = (
                    min(remaining, 0.05)
                    if self._pause_event is not None
                    else remaining
                )
                self._sleep(sleep_time)

            if (
                self._pause_event is not None
                and not self._pause_event.is_set()
            ):
                self._rebase()
                continue
            if self._monotonic() >= target_wall_time:
                break

        self.current_simulation_time = simulation_timestamp

    def _rebase(self):
        self._anchor_wall_time = self._monotonic()
        self._anchor_simulation_time = self.current_simulation_time
