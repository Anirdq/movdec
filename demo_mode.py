"""
WiFi Movement Detection System
================================
demo_mode.py — Synthetic RSSI data generator for testing without
               physical WiFi hardware or admin privileges.

Simulates realistic RSSI fluctuations with configurable movement episodes
so that the full detection + visualisation pipeline can be validated offline.
"""

import math
import random
import time
import logging

logger = logging.getLogger(__name__)

# ── Simulation parameters ─────────────────────────────────────────────────────
_BASE_RSSI       = -55.0   # dBm — typical "good signal" baseline
_NOISE_LEVEL     =   1.5   # dBm — ambient noise std dev (no movement)
_MOVEMENT_NOISE  =   6.0   # dBm — elevated noise during simulated movement
_MOVEMENT_PERIOD =  20      # seconds — how often a "motion episode" starts
_MOVEMENT_DURATION=  8      # seconds — how long each episode lasts
_SLOW_DRIFT_AMP  =   2.0   # dBm — slow sinusoidal drift amplitude
_SLOW_DRIFT_FREQ = 0.03     # Hz  — drift frequency

_start_time = time.time()


def get_simulated_rssi() -> float:
    """
    Return a synthetic RSSI value that mimics real-world WiFi behaviour.

    Behaviour:
      - Constant base level (e.g. -55 dBm).
      - Slow sinusoidal drift to simulate temperature / multipath changes.
      - Low Gaussian noise during quiet periods.
      - Elevated Gaussian noise during simulated movement episodes.

    Returns:
        Synthetic RSSI in dBm (float, typically -40 to -75).
    """
    elapsed = time.time() - _start_time

    # Slow environmental drift
    drift = _SLOW_DRIFT_AMP * math.sin(2 * math.pi * _SLOW_DRIFT_FREQ * elapsed)

    # Decide if we're in a "movement" episode
    cycle_position = elapsed % _MOVEMENT_PERIOD
    in_movement = cycle_position < _MOVEMENT_DURATION

    noise_std = _MOVEMENT_NOISE if in_movement else _NOISE_LEVEL
    noise = random.gauss(0, noise_std)

    rssi = _BASE_RSSI + drift + noise

    logger.debug(
        f"Demo RSSI: {rssi:.2f} dBm | "
        f"{'[MOVING]' if in_movement else '[STILL]'} | "
        f"noise_std={noise_std}"
    )
    return rssi
