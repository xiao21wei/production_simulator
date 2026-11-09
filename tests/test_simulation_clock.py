import threading
import time
import unittest

from simulator.clock import SimulationClock


class FakeTime:
    def __init__(self, now=100.0):
        self.now = now
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class SimulationClockTest(unittest.TestCase):
    def test_default_speed_is_ten_times(self):
        clock = SimulationClock()

        self.assertEqual(clock.speed, 10.0)

    def test_time_steps_are_related_by_speed(self):
        clock = SimulationClock(real_time_step=0.1, speed=10)

        self.assertEqual(clock.simulation_time_step, 1.0)

        clock.speed = 20

        self.assertEqual(clock.speed, 20)
        self.assertEqual(clock.simulation_time_step, 2.0)

    def test_wait_uses_speed_multiplier(self):
        fake_time = FakeTime()
        clock = SimulationClock(
            speed=10,
            monotonic_fn=fake_time.monotonic,
            sleep_fn=fake_time.sleep,
        )
        clock.start()

        clock.wait_until(20)
        clock.wait_until(30)

        self.assertEqual(fake_time.sleeps, [2.0, 1.0])
        self.assertEqual(clock.current_simulation_time, 30.0)

    def test_fast_forward_does_not_sleep(self):
        fake_time = FakeTime()
        clock = SimulationClock(
            realtime=False,
            monotonic_fn=fake_time.monotonic,
            sleep_fn=fake_time.sleep,
        )
        clock.start()

        clock.wait_until(1000)

        self.assertEqual(fake_time.sleeps, [])
        self.assertEqual(clock.current_simulation_time, 1000.0)

    def test_speed_change_rebases_clock(self):
        fake_time = FakeTime()
        clock = SimulationClock(
            speed=10,
            monotonic_fn=fake_time.monotonic,
            sleep_fn=fake_time.sleep,
        )
        clock.start()
        clock.wait_until(20)

        fake_time.now += 0.5
        clock.speed = 20
        clock.wait_until(40)

        self.assertEqual(fake_time.sleeps, [2.0, 1.0])

    def test_invalid_time_settings_are_rejected(self):
        for kwargs in (
            {"real_time_step": 0},
            {"speed": 0},
            {"speed": float("inf")},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    SimulationClock(**kwargs)

    def test_pause_blocks_clock_until_resume(self):
        fake_time = FakeTime()
        pause_event = threading.Event()
        pause_event.set()
        clock = SimulationClock(
            speed=10,
            monotonic_fn=fake_time.monotonic,
            sleep_fn=fake_time.sleep,
        )
        clock.set_pause_event(pause_event)
        clock.start()
        pause_event.clear()

        waiter = threading.Thread(target=clock.wait_until, args=(20,))
        waiter.start()
        time.sleep(0.05)

        self.assertTrue(waiter.is_alive())
        self.assertEqual(clock.current_simulation_time, 0.0)

        pause_event.set()
        waiter.join(timeout=1)

        self.assertFalse(waiter.is_alive())
        self.assertEqual(clock.current_simulation_time, 20.0)


if __name__ == "__main__":
    unittest.main()
