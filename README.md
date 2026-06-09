# Camera

A smooth, human-like camera controller for [Minescript](https://minescript.net/) (Minecraft mod). Moves the player's view to a target using eased motion, optional arc curves, and configurable jitter.

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

## Methods

| Method | Description |
|---|---|
| `update_target(target)` | Set a new look target and start/continue tracking. Accepts `(x, y, z)` block coords or `(yaw, pitch)`. |
| `single_look(target)` | Look at target once on the calling thread, then stop. |
| `stop()` | Cancel any in-progress movement. |

## Helper

```python
from Camera import get_relative_angles

rel_yaw, rel_pitch = get_relative_angles((x, y, z))
```

Returns the yaw and pitch offsets from the player's current orientation to a block.
