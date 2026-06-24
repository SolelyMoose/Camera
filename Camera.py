import minescript
import random
import time
import math
import threading
import os

EYE_HEIGHT = 1.62
BASE_DELAY = 0.001
_ENTITY_TICK = 0.05

def _read_sensitivity():
    options = os.path.join(os.path.dirname(__file__), '..', 'options.txt')
    try:
        with open(options) as f:
            for line in f:
                if line.startswith('mouseSensitivity:'):
                    return float(line.split(':', 1)[1].strip())
    except Exception:
        pass
    return 0.5

sensitivity = _read_sensitivity()

def normalize(angle):
    return (angle + 180) % 360 - 180

class Camera:
    def __init__(self, steps=120, curve_strength=0.05, jitter=0,
                 phase_split=0.6, rough_stop=0.7, extra_delay=0,
                 refine_threshold=1.5, refine_time=4.0,
                 refine=False):
        self.steps = steps
        self.curve_strength = curve_strength
        self.jitter = jitter
        self.jitter_interval = 20
        self.jitter_smoothing = 0.08
        self.phase_split = phase_split
        self.rough_stop = rough_stop
        self.extra_delay = extra_delay
        self.refine_threshold = refine_threshold
        self.refine_time = refine_time
        self.sensitivity = sensitivity
        self.refine = refine
        self._target = None
        self._tracking = False
        self._lock = threading.Lock()
        self._generation = 0
        self._trigger = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        self._entity_tracking = False
        self._entity_filter = {}
        self._entity_thread = None
        
    @staticmethod
    def _calc_gcd(sensitivity):
        f = sensitivity * 0.6 + 0.2
        return f * f * f * 8.0 * 0.15

    def _snap(self, delta):
        gcd = self._calc_gcd(self.sensitivity)
        if gcd <= 0:
            return delta
        return round(delta / gcd) * gcd

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

    def _do_lookat(self, target, gen, phase2_async=False):
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
        last_y, last_p = yaw, pitch

        def _step(t, frac, curve_scale, jitter_scale, delay=None):
            nonlocal jitter_y, jitter_p, target_jitter_y, target_jitter_p, step_count, last_y, last_p
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
            desired_y = base_yaw + perp_yaw * curve_factor + jitter_y
            desired_p = base_pitch + perp_pitch * curve_factor + jitter_p
            next_y = last_y + self._snap(desired_y - last_y)
            next_p = last_p + self._snap(desired_p - last_p)
            last_y, last_p = next_y, next_p
            minescript.player_set_orientation(next_y, next_p)
            actual_delay = ((BASE_DELAY + self.extra_delay) / speed_mult) if delay is None else delay
            time.sleep(max(0, actual_delay + random.uniform(-0.001, 0.001)))
            return True

        # Phase 1: move toward target (all the way if refine=False)
        if self.refine and total_delta > self.refine_threshold:
            phase1_end_frac = 1.0 - self.refine_threshold / total_delta
        else:
            phase1_end_frac = 1.0

        phase1_steps = max(5, int(steps * phase1_end_frac))
        for i in range(1, phase1_steps + 1):
            t = i / phase1_steps
            frac = phase1_end_frac * (1 - math.cos(math.pi * t)) / 2
            if not _step(t, frac, curve_scale=1.0, jitter_scale=math.sin(math.pi * t)):
                return

        if not self.refine:
            return

        # Phase 2: slow refinement to exact over refine_time seconds
        refine_steps = 200
        refine_delay = self.refine_time / refine_steps

        def _run_phase2():
            for i in range(1, refine_steps + 1):
                t = i / refine_steps
                sub_frac = (1 - math.cos(math.pi * t)) / 2
                frac = phase1_end_frac + (1.0 - phase1_end_frac) * sub_frac
                if not _step(t, frac, curve_scale=0.0, jitter_scale=0.0, delay=refine_delay):
                    return

        if phase2_async:
            threading.Thread(target=_run_phase2, daemon=True).start()
        else:
            _run_phase2()

    def single_look(self, target, steps=None, curve_strength=None, phase_split=None,
                    rough_stop=None, extra_delay=None, refine_threshold=None, refine_time=None,
                    sensitivity=None, refine=None, background_refine=False):
        with self._lock:
            self._target = None
            self._tracking = False
            self._generation += 1
            gen = self._generation
        overrides = {k: v for k, v in [('steps', steps), ('curve_strength', curve_strength),
                                        ('phase_split', phase_split), ('rough_stop', rough_stop),
                                        ('extra_delay', extra_delay), ('refine_threshold', refine_threshold),
                                        ('refine_time', refine_time), ('sensitivity', sensitivity),
                                        ('refine', refine)] if v is not None}
        saved = {k: getattr(self, k) for k in overrides}
        for k, v in overrides.items():
            setattr(self, k, v)
        try:
            self._do_lookat(target, gen, phase2_async=background_refine)
        finally:
            for k, v in saved.items():
                setattr(self, k, v)

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
            self._entity_tracking = False
            self._entity_filter = {}
        self._trigger.set()

    # --- entity tracking ---

    @staticmethod
    def _find_entity(name, entity_type, uuid):
        kwargs = {"sort": "nearest", "limit": 20}
        if name is not None:
            kwargs["name"] = name
        if entity_type is not None:
            kwargs["type"] = entity_type
        if uuid is not None:
            kwargs["uuid"] = uuid
        for e in minescript.entities(**kwargs):
            if not e.local:
                return e
        return None

    @staticmethod
    def _entity_aim_angles(entity, aim_height):
        px, py, pz = minescript.player_position()
        pos = entity.lerp_position or entity.position
        dx = pos[0] - px
        dy = (pos[1] + aim_height) - (py + EYE_HEIGHT)
        dz = pos[2] - pz
        horiz = math.hypot(dx, dz)
        yaw = -math.degrees(math.atan2(dx, dz))
        pitch = -math.degrees(math.atan2(dy, horiz))
        return yaw, pitch

    def _entity_worker(self):
        while True:
            with self._lock:
                if not self._entity_tracking:
                    return
                f = dict(self._entity_filter)

            entity = self._find_entity(f.get("name"), f.get("entity_type"), f.get("uuid"))
            if entity is not None:
                px, py, pz = minescript.player_position()
                pos = entity.lerp_position or entity.position
                dist = math.sqrt((pos[0]-px)**2 + (pos[1]-py)**2 + (pos[2]-pz)**2)
                if dist <= f["max_distance"]:
                    yaw, pitch = self._entity_aim_angles(entity, f["aim_height"])
                    self.update_target((yaw, pitch))
                else:
                    self.stop()

            time.sleep(_ENTITY_TICK)

    def entities_in_front(self, fov=60, max_distance=32, **kwargs):
        px, py, pz = minescript.player_position()
        yaw, pitch = minescript.player_orientation()
        yaw_r = math.radians(yaw)
        pitch_r = math.radians(pitch)
        lx = -math.sin(yaw_r) * math.cos(pitch_r)
        ly = -math.sin(pitch_r)
        lz = math.cos(yaw_r) * math.cos(pitch_r)

        half_fov = fov / 2
        result = []
        search_kwargs = {"sort": "nearest", "limit": 50}
        search_kwargs.update(kwargs)

        for entity in minescript.entities(**search_kwargs):
            if entity.local:
                continue
            pos = entity.lerp_position or entity.position
            dx = pos[0] - px
            dy = pos[1] - (py + EYE_HEIGHT)
            dz = pos[2] - pz
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            if dist == 0 or dist > max_distance:
                continue
            dot = (dx*lx + dy*ly + dz*lz) / dist
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            if angle <= half_fov:
                result.append(entity)

        return result
    
    def track_entity(self, name=None, entity_type=None, uuid=None,
                     max_distance=64.0, aim_height=1.0):
        print("Tracking entity")
        """Continuously aim at the nearest matching entity.

        Filter by name (regex), entity_type (regex, e.g. 'minecraft:zombie'),
        or uuid (exact). Call stop() to cancel.
        """
        if not any([name, entity_type, uuid]):
            raise ValueError("track_entity: provide at least one of name, entity_type, or uuid")
        with self._lock:
            self._entity_filter = {
                "name": name,
                "entity_type": entity_type,
                "uuid": uuid,
                "max_distance": max_distance,
                "aim_height": aim_height,
            }
            self._entity_tracking = True
        if self._entity_thread is None or not self._entity_thread.is_alive():
            self._entity_thread = threading.Thread(target=self._entity_worker, daemon=True)
            self._entity_thread.start()

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

#camera.track_entity(entity_type="minecraft:zombie")

#camera.update_target((-34, -61, 41))
#camera._run_loop()

#camera.single_look((95, -60, 301))