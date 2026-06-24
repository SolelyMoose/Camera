# Camera

A smooth, human-like camera controller for [Minescript](https://minescript.net/) (Minecraft mod). Moves the player's view to a target using eased motion, optional arc curves, configurable jitter, and GCD-snapped rotations that match real mouse input.

## Requirements

- Minecraft with [Minescript](https://minescript.net/) installed

## Usage

```python
from Camera import Camera

camera = Camera()

# Look at a block (x, y, z)
camera.update_target((-34, -61, 41))

# Look at an explicit (yaw, pitch)
camera.update_target((-90.0, 15.0))

# One-shot look (blocks until complete)
camera.single_look((-34, -61, 41))

# Stop tracking
camera.stop()
```

## Constructor Parameters

| Parameter | Default | Description |
|---|---|---|
| `steps` | `120` | Number of interpolation steps for a 90° turn. Fewer = faster. |
| `curve_strength` | `0.05` | How much the path arcs sideways mid-turn. |
| `jitter` | `0` | Random deviation added each step, simulating hand movement. |
| `phase_split` | `0.6` | For turns > 180°, fraction of steps spent in the rough phase. |
| `rough_stop` | `0.7` | Fraction of the angle covered during the rough phase. |
| `extra_delay` | `0` | Additional seconds of sleep added per step. |
| `refine` | `False` | When `True`, adds a slow phase 2 that creeps to the exact target angle over `refine_time` seconds. |
| `refine_threshold` | `1.5` | Degrees from target at which phase 1 stops and phase 2 begins (only used when `refine=True`). |
| `refine_time` | `4.0` | Seconds spent in the refinement phase (only used when `refine=True`). |

Sensitivity is read automatically from `options.txt` and used to compute the GCD — the minimum angular step Minecraft's mouse handler can produce. Every rotation is snapped to a multiple of this value so movement is indistinguishable from real mouse input.

## Methods

| Method | Description |
|---|---|
| `update_target(target)` | Set a new look target and start/continue tracking. Accepts `(x, y, z)` block coords or `(yaw, pitch)`. |
| `single_look(target, ...)` | Look at target once on the calling thread, then stop. Accepts the same keyword overrides as the constructor. |
| `stop()` | Cancel any in-progress movement. |
| `track_entity(...)` | Continuously aim at the nearest matching entity. Filter by `name`, `entity_type`, or `uuid`. Call `stop()` to cancel. |
| `entities_in_front(fov, max_distance)` | Returns a list of entities within `fov` degrees of the player's current look direction. |

## Helper

```python
from Camera import get_relative_angles

rel_yaw, rel_pitch = get_relative_angles((x, y, z))
```

Returns the yaw and pitch offsets from the player's current orientation to a block.
