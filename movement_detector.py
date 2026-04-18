"""
WiFi Movement Detection System
================================
movement_detector.py — Core detection logic.

Classifies the current signal state as "Movement Detected" or "No Movement"
by comparing the computed variance against a configurable threshold.

Also tracks detection events with timestamps for logging / plotting.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DetectionStatus(Enum):
    """Possible states the movement detector can report."""
    MOVEMENT = "Movement Detected"
    NO_MOVEMENT = "No Movement"
    INSUFFICIENT_DATA = "Collecting Data..."


@dataclass
class DetectionResult:
    """
    A single detection result snapshot.

    Attributes:
        timestamp     : Unix epoch time of this reading.
        raw_rssi      : Raw (unfiltered) RSSI from the scanner in dBm.
        smoothed_rssi : Moving-average filtered RSSI value.
        variance      : Variance computed over the sliding window.
        std_dev       : Standard deviation over the sliding window.
        status        : Classified detection status (enum).
        threshold     : The variance threshold used for classification.
    """
    timestamp: float
    raw_rssi: float
    smoothed_rssi: float
    variance: float
    std_dev: float
    status: DetectionStatus
    threshold: float


@dataclass
class DetectionHistory:
    """
    Maintains a rolling log of the most recent DetectionResult snapshots.
    Useful for plotting and post-analysis.
    """
    max_records: int = 500
    records: list[DetectionResult] = field(default_factory=list)

    def add(self, result: DetectionResult) -> None:
        """Append a result, trimming excess records from the front."""
        self.records.append(result)
        if len(self.records) > self.max_records:
            self.records.pop(0)

    def timestamps(self) -> list[float]:
        return [r.timestamp for r in self.records]

    def raw_rssi_values(self) -> list[float]:
        return [r.raw_rssi for r in self.records]

    def smoothed_rssi_values(self) -> list[float]:
        return [r.smoothed_rssi for r in self.records]

    def variances(self) -> list[float]:
        return [r.variance for r in self.records]

    def statuses(self) -> list[DetectionStatus]:
        return [r.status for r in self.records]


class MovementDetector:
    """
    Classifies WiFi RSSI signal variance into movement or no-movement states.

    The core insight: when a person moves through a room, they reflect and
    absorb WiFi signals differently, causing measurable fluctuations (higher
    variance) in the RSSI received by a device. A stationary or empty room
    produces a comparatively stable (low variance) signal.

    Tuning:
        - Lower `threshold`  → More sensitive (more false positives).
        - Higher `threshold` → Less sensitive (may miss subtle movement).
        - Typical range: 1.0 – 10.0 (depends on environment).
    """

    def __init__(self, variance_threshold: float = 3.0, min_samples: int = 5):
        """
        Args:
            variance_threshold: Variance above which movement is declared.
            min_samples       : Minimum number of samples before attempting classification.
        """
        if variance_threshold <= 0:
            raise ValueError("Variance threshold must be a positive number.")
        if min_samples < 2:
            raise ValueError("min_samples must be at least 2 to compute variance.")

        self.variance_threshold = variance_threshold
        self.min_samples = min_samples
        self.history = DetectionHistory()

        logger.info(
            f"MovementDetector initialised | "
            f"threshold={variance_threshold} | min_samples={min_samples}"
        )

    def classify(
        self,
        raw_rssi: float,
        smoothed_rssi: float,
        variance: float,
        std_dev: float,
        sample_count: int,
    ) -> DetectionResult:
        """
        Determine movement status from the current signal statistics.

        Args:
            raw_rssi      : Latest unfiltered RSSI reading.
            smoothed_rssi : Latest moving-average filtered RSSI.
            variance      : Current sliding-window variance.
            std_dev       : Current sliding-window standard deviation.
            sample_count  : Total number of samples collected so far.

        Returns:
            A DetectionResult dataclass capturing the full snapshot.
        """
        if sample_count < self.min_samples:
            status = DetectionStatus.INSUFFICIENT_DATA
        elif variance > self.variance_threshold:
            status = DetectionStatus.MOVEMENT
        else:
            status = DetectionStatus.NO_MOVEMENT

        result = DetectionResult(
            timestamp=time.time(),
            raw_rssi=raw_rssi,
            smoothed_rssi=smoothed_rssi,
            variance=variance,
            std_dev=std_dev,
            status=status,
            threshold=self.variance_threshold,
        )

        self.history.add(result)
        logger.debug(f"Classified: {status.value} (var={variance:.4f})")
        return result

    def set_threshold(self, new_threshold: float) -> None:
        """Dynamically update the variance threshold at runtime."""
        if new_threshold <= 0:
            raise ValueError("Threshold must be positive.")
        logger.info(f"Threshold updated: {self.variance_threshold} → {new_threshold}")
        self.variance_threshold = new_threshold
