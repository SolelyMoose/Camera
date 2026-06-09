import minescript
import random
import time
import math
import threading

EYE_HEIGHT = 1.62
BASE_DELAY = 0.001


def normalize(angle):
    return (angle + 180) % 360 - 180


class Camera:
    def __init__(self, steps=120, curve_strength=0.05, jitter=0,
                 phase_split=0.6, rough_stop=0.7, extra_delay=0):
        self.steps = steps
        self.curve_strength = curve_strength
        self.jitter = jitter
        self.jitter_interval = 20
        self.jitter_smoothing = 0.08
        self.phase_split = phase_split
        self.rough_stop = rough_stop
        self.extra_delay = extra_delay
        self._target = None
        self._tracking = False
        self._lock = threading.Lock()
        self._generation = 0
        self._trigger = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while True:
            self._trigger.wait()
            self._trigger.clear()
            self._run_loop()

    def _run_loop(self):
        while True:
            with self._lock:
                target = self._target
                tracking = self._tracking
                gen = self._generation
            if target is None:
                return
            self._do_lookat(target, gen)
            with self._lock:
                changed = self._generation != gen
                still_tracking = self._tracking
                still_has_target = self._target is not None
            if changed:
                continue
            if still_tracking and still_has_target:
                continue
            return

    def _do_lookat(self, target, gen):
        if minescript.screen_name() is not None:
            return
        px, py, pz = minescript.player_position()
        yaw, pitch = minescript.player_orientation()

        is_orientation = len(target) == 2
        if is_orientation:
            desired_yaw, desired_pitch = target
        else:
            ex, ey, ez = px, py + EYE_HEIGHT, pz
            x, y, z = target
            dx, dy, dz = x + 0.5 - ex, y + 0.5 - ey, z + 0.5 - ez
            if self.jitter > 0:
                distance = math.sqrt(dx*dx + dy*dy + dz*dz)
                deviation = min(0.45, 2.0 / max(distance, 0.1)) * self.jitter
                dx += random.uniform(-deviation, deviation)
                dy += random.uniform(-deviation, deviation)
                dz += random.uniform(-deviation, deviation)
            horiz = math.hypot(dx, dz)
            desired_yaw = -math.degrees(math.atan2(dx, dz))
            desired_pitch = -math.degrees(math.atan2(dy, horiz))

        delta_y = normalize(desired_yaw - yaw)
        delta_p = normalize(desired_pitch - pitch)
        total_delta = math.hypot(delta_y, delta_p)
        steps = max(10, int(self.steps * min(total_delta / 90.0, 1.0)))

        speed_mult = max(1.0, total_delta / 45.0)

        if total_delta > 0:
            perp_yaw = -delta_p / total_delta
            perp_pitch = delta_y / total_delta
        else:
            perp_yaw = perp_pitch = 0.0

        jitter_y = jitter_p = 0.0
        target_jitter_y = target_jitter_p = 0.0
        step_count = 0

        def _step(t, frac, curve_scale, jitter_scale, delay=None):
            nonlocal jitter_y, jitter_p, target_jitter_y, target_jitter_p, step_count
            if self._generation != gen:
                return False
            if self.jitter > 0 and step_count % self.jitter_interval == 0:
                target_jitter_y = random.uniform(-self.jitter, self.jitter) * jitter_scale
                target_jitter_p = random.uniform(-self.jitter, self.jitter) * jitter_scale
            jitter_y += (target_jitter_y - jitter_y) * self.jitter_smoothing
            jitter_p += (target_jitter_p - jitter_p) * self.jitter_smoothing
            step_count += 1
            base_yaw = yaw + delta_y * frac
            base_pitch = pitch + delta_p * frac
            curve_factor = math.sin(math.pi * t) * self.curve_strength * min(total_delta, 60.0) * curve_scale
            next_y = base_yaw + perp_yaw * curve_factor + jitter_y
            next_p = base_pitch + perp_pitch * curve_factor + jitter_p
            minescript.player_set_orientation(next_y, next_p)
            actual_delay = ((BASE_DELAY + self.extra_delay) / speed_mult) if delay is None else delay
            time.sleep(max(0, actual_delay + random.uniform(-0.001, 0.001)))
            return True

        if total_delta > 180:
            phase1_steps = int(steps * self.phase_split)
            phase2_steps = steps - phase1_steps
            phase2_delay = BASE_DELAY * 12 if is_orientation else BASE_DELAY

            for i in range(1, phase1_steps + 1):
                t = i / phase1_steps
                frac = self.rough_stop * (1 - math.cos(math.pi * t)) / 2
                if not _step(t, frac, curve_scale=1.0, jitter_scale=math.sin(math.pi * t)):
                    return

            for i in range(1, phase2_steps + 1):
                t = i / phase2_steps
                frac = self.rough_stop + (1 - self.rough_stop) * (1 - math.cos(math.pi * t)) / 2
                if not _step(t, frac, curve_scale=0.25, jitter_scale=math.sin(math.pi * t) * 0.25, delay=phase2_delay):
                    return
        else:
            for i in range(1, steps + 1):
                t = i / steps
                frac = (1 - math.cos(math.pi * t)) / 2
                if not _step(t, frac, curve_scale=1.0, jitter_scale=math.sin(math.pi * t)):
                    return

    def single_look(self, target):
        # Cancel background work and run on the calling thread so it completes fully.
        with self._lock:
            self._target = None
            self._tracking = False
            self._generation += 1
            gen = self._generation
        self._do_lookat(target, gen)

    def update_target(self, target):
        with self._lock:
            if self._target == target and self._tracking:
                return
            self._target = target
            self._tracking = True
            self._generation += 1
        self._trigger.set()

    def stop(self):
        with self._lock:
            self._target = None
            self._tracking = False
            self._generation += 1
        self._trigger.set()

def get_relative_angles(block):
    px, py, pz = minescript.player_position()
    yaw0, pitch0 = minescript.player_orientation()
    ex, ey, ez = px, py + EYE_HEIGHT, pz
    x, y, z = block
    dx, dy, dz = x + 0.5 - ex, y + 0.5 - ey, z + 0.5 - ez
    horiz = math.hypot(dx, dz)
    rel_yaw = normalize(-math.degrees(math.atan2(dx, dz)) - yaw0)
    rel_pitch = normalize(-math.degrees(math.atan2(dy, horiz)) - pitch0)
    return rel_yaw, rel_pitch


#camera = Camera()
#camera.update_target((-34, -61, 41))
#camera._run_loop()
#camera.single_look((-34, -61, 41))