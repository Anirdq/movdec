"""
WiFi Movement Detection System
================================
signal_processor.py — Module for RSSI signal processing.

Provides:
  - RingBuffer: Fixed-size circular buffer for time-series storage.
  - MovingAverageFilter: Smooths noisy RSSI readings.
  - VarianceCalculator: Calculates variance/std-dev over a sliding window.
"""
from __future__ import annotations

from collections import deque
import numpy as np
import logging

logger = logging.getLogger(__name__)


class RingBuffer:
    """
    A fixed-size circular (ring) buffer for storing a time-series of RSSI values.

    When the buffer is full, the oldest value is automatically discarded
    to make room for the newest one — ideal for sliding-window analysis.
    """

    def __init__(self, maxlen: int):
        """
        Args:
            maxlen: Maximum number of samples to store.
        """
        if maxlen <= 0:
            raise ValueError("Buffer size must be a positive integer.")
        self._buffer: deque[float] = deque(maxlen=maxlen)
        self.maxlen = maxlen

    def append(self, value: float) -> None:
        """Add a new sample to the buffer."""
        self._buffer.append(value)

    def get(self) -> list[float]:
        """Return all current samples as a plain list."""
        return list(self._buffer)

    def is_full(self) -> bool:
        """Return True when the buffer has reached its maximum capacity."""
        return len(self._buffer) == self.maxlen

    def __len__(self) -> int:
        return len(self._buffer)

    def __repr__(self) -> str:
        return f"RingBuffer(maxlen={self.maxlen}, current={len(self._buffer)})"


class MovingAverageFilter:
    """
    Computes a simple moving average (SMA) over a sliding window of RSSI samples.

    Moving average smooths out high-frequency noise spikes in the signal,
    making variance-based movement detection more reliable.
    """

    def __init__(self, window_size: int):
        """
        Args:
            window_size: Number of samples to average over.
        """
        if window_size <= 0:
            raise ValueError("Window size must be a positive integer.")
        self.window_size = window_size

    def apply(self, samples: list[float]) -> float:
        """
        Compute the moving average of the most recent `window_size` samples.

        Args:
            samples: The full list of raw RSSI values.

        Returns:
            Smoothed RSSI value (mean of last window_size samples).
        """
        if not samples:
            logger.warning("MovingAverageFilter received an empty sample list.")
            return 0.0

        # Use at most the last `window_size` values
        window = samples[-self.window_size:]
        smoothed = float(np.mean(window))
        logger.debug(f"MA applied over {len(window)} samples → {smoothed:.2f} dBm")
        return smoothed

    def apply_to_series(self, samples: list[float]) -> list[float]:
        """
        Apply the moving average across the entire sample history.

        Useful for plotting the smoothed signal over time.

        Args:
            samples: Full list of raw RSSI values.

        Returns:
            List of smoothed values (same length as input, padded with first value).
        """
        if len(samples) < self.window_size:
            # Not enough samples yet — return as-is
            return samples[:]

        smoothed: list[float] = []
        for i in range(len(samples)):
            start = max(0, i - self.window_size + 1)
            window = samples[start : i + 1]
            smoothed.append(float(np.mean(window)))

        return smoothed


class VarianceCalculator:
    """
    Calculates the variance and standard deviation of RSSI samples
    within a sliding window.

    Higher variance → more signal fluctuation → likely human movement nearby.
    Lower variance → stable signal → room likely empty.
    """

    def __init__(self, window_size: int):
        """
        Args:
            window_size: Number of most-recent samples to analyse.
        """
        if window_size <= 0:
            raise ValueError("Window size must be a positive integer.")
        self.window_size = window_size

    def variance(self, samples: list[float]) -> float:
        """
        Compute variance of the last `window_size` samples.

        Args:
            samples: List of RSSI values.

        Returns:
            Variance value (float). Returns 0.0 on insufficient data.
        """
        if len(samples) < 2:
            return 0.0
        window = samples[-self.window_size:]
        var = float(np.var(window))
        logger.debug(f"Variance over last {len(window)} samples: {var:.4f}")
        return var

    def std_dev(self, samples: list[float]) -> float:
        """
        Compute standard deviation of the last `window_size` samples.

        Args:
            samples: List of RSSI values.

        Returns:
            Standard deviation value (float). Returns 0.0 on insufficient data.
        """
        if len(samples) < 2:
            return 0.0
        window = samples[-self.window_size:]
        std = float(np.std(window))
        logger.debug(f"Std Dev over last {len(window)} samples: {std:.4f}")
        return std
