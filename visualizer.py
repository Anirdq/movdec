"""
WiFi Movement Detection System
================================
visualizer.py — Real-time matplotlib dashboard for RSSI monitoring.

Displays three synchronized panels:
  1. Raw RSSI vs smoothed RSSI over time.
  2. Variance over time with threshold line.
  3. Movement detection status (colour-coded band).

Uses matplotlib's animation framework for a non-blocking live update loop.
"""
from __future__ import annotations

import time
import threading
import logging
from typing import Callable

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation
from matplotlib.lines import Line2D

from movement_detector import DetectionStatus, DetectionHistory

logger = logging.getLogger(__name__)

# ── Colour scheme ─────────────────────────────────────────────────────────────
COLOUR_RAW       = "#4FC3F7"   # Light blue  — raw RSSI
COLOUR_SMOOTHED  = "#FF8A65"   # Coral       — smoothed RSSI
COLOUR_VARIANCE  = "#CE93D8"   # Lavender    — variance
COLOUR_THRESHOLD = "#EF5350"   # Red         — threshold line
COLOUR_MOVEMENT  = "#FF1744"   # Bright red  — movement band
COLOUR_NONE      = "#00E676"   # Green       — no movement band
COLOUR_PENDING   = "#FFC400"   # Amber       — insufficient data band
BG_DARK          = "#0D1117"   # GitHub dark background
PANEL_BG         = "#161B22"   # Slightly lighter panel
GRID_COLOUR      = "#30363D"   # Subtle grid lines
TEXT_COLOUR      = "#C9D1D9"   # Light grey text


def _style_axis(ax: plt.Axes, title: str, ylabel: str) -> None:
    """Apply dark-theme styling to a matplotlib axis."""
    ax.set_facecolor(PANEL_BG)
    ax.set_title(title, color=TEXT_COLOUR, fontsize=11, fontweight="bold", pad=8)
    ax.set_ylabel(ylabel, color=TEXT_COLOUR, fontsize=9)
    ax.set_xlabel("Time (seconds ago)", color=TEXT_COLOUR, fontsize=9)
    ax.tick_params(colors=TEXT_COLOUR, labelsize=8)
    ax.spines["bottom"].set_color(GRID_COLOUR)
    ax.spines["top"].set_color(GRID_COLOUR)
    ax.spines["left"].set_color(GRID_COLOUR)
    ax.spines["right"].set_color(GRID_COLOUR)
    ax.grid(True, color=GRID_COLOUR, linestyle="--", linewidth=0.5, alpha=0.6)


class RealTimePlotter:
    """
    Manages a live matplotlib figure that updates every `interval_ms` milliseconds.

    Architecture:
        - The main thread owns the matplotlib figure (required on most backends).
        - A separate data-collection thread supplies RSSI readings via a
          shared `DetectionHistory` object that is polled on each animation tick.
    """

    def __init__(
        self,
        history: DetectionHistory,
        ssid: str,
        interval_ms: int = 1000,
        window_seconds: int = 60,
    ):
        """
        Args:
            history        : Shared DetectionHistory updated by the main loop.
            ssid           : SSID being monitored (shown in figure title).
            interval_ms    : Refresh rate of the plot in milliseconds.
            window_seconds : How many seconds of history to display.
        """
        self.history = history
        self.ssid = ssid
        self.interval_ms = interval_ms
        self.window_seconds = window_seconds
        self._anim: FuncAnimation | None = None

        matplotlib.rcParams["font.family"] = "monospace"
        self._build_figure()

    def _build_figure(self) -> None:
        """Create the figure layout with three stacked subplots."""
        self.fig, (self.ax_rssi, self.ax_var, self.ax_status) = plt.subplots(
            3, 1, figsize=(13, 8), sharex=False
        )
        self.fig.patch.set_facecolor(BG_DARK)
        self.fig.suptitle(
            f"[*] WiFi Movement Detector  |  SSID: {self.ssid}",
            color=TEXT_COLOUR,
            fontsize=14,
            fontweight="bold",
            y=0.98,
        )
        plt.subplots_adjust(hspace=0.45, top=0.93, bottom=0.08)

        # ── Panel 1: RSSI ──────────────────────────────────────────────────
        _style_axis(self.ax_rssi, "RSSI Signal Strength", "RSSI (dBm)")
        self.line_raw,      = self.ax_rssi.plot([], [], color=COLOUR_RAW,      lw=1.2,
                                                 label="Raw RSSI",      alpha=0.7)
        self.line_smoothed, = self.ax_rssi.plot([], [], color=COLOUR_SMOOTHED, lw=2.0,
                                                 label="Smoothed RSSI")
        self.ax_rssi.legend(
            handles=[
                Line2D([0], [0], color=COLOUR_RAW,      lw=1.5, label="Raw RSSI"),
                Line2D([0], [0], color=COLOUR_SMOOTHED, lw=2.0, label="Smoothed (MA)"),
            ],
            facecolor=PANEL_BG, labelcolor=TEXT_COLOUR, fontsize=8,
        )

        # ── Panel 2: Variance ──────────────────────────────────────────────
        _style_axis(self.ax_var, "Signal Variance (Sliding Window)", "Variance")
        self.line_var,       = self.ax_var.plot([], [], color=COLOUR_VARIANCE,  lw=1.8,
                                                 label="Variance")
        self.line_threshold, = self.ax_var.plot([], [], color=COLOUR_THRESHOLD, lw=1.5,
                                                 linestyle="--", label="Threshold")
        self.ax_var.legend(
            handles=[
                Line2D([0], [0], color=COLOUR_VARIANCE,  lw=1.8, label="Variance"),
                Line2D([0], [0], color=COLOUR_THRESHOLD, lw=1.5,
                       linestyle="--", label="Threshold"),
            ],
            facecolor=PANEL_BG, labelcolor=TEXT_COLOUR, fontsize=8,
        )

        # ── Panel 3: Status band ───────────────────────────────────────────
        _style_axis(self.ax_status, "Movement Detection Status", "Status")
        self.ax_status.set_yticks([0, 1, 2])
        self.ax_status.set_yticklabels(
            ["No Movement", "Collecting…", "MOVEMENT"], color=TEXT_COLOUR, fontsize=8
        )
        self.ax_status.set_ylim(-0.5, 2.5)
        self.line_status, = self.ax_status.plot([], [], color=COLOUR_MOVEMENT, lw=2.0)

        # Status legend patches
        self.ax_status.legend(
            handles=[
                mpatches.Patch(color=COLOUR_NONE,     label="No Movement"),
                mpatches.Patch(color=COLOUR_PENDING,  label="Collecting Data"),
                mpatches.Patch(color=COLOUR_MOVEMENT, label="Movement Detected"),
            ],
            facecolor=PANEL_BG, labelcolor=TEXT_COLOUR, fontsize=8, loc="upper left",
        )

        # Persistent status text label (top-right of RSSI panel)
        self.status_text = self.fig.text(
            0.98, 0.95, "●  Initialising…",
            color=COLOUR_PENDING, fontsize=11, fontweight="bold",
            ha="right", va="top",
        )

    def _update(self, _frame: int) -> list:
        """
        Animation callback — called every `interval_ms` milliseconds.

        Reads the latest data from the shared DetectionHistory and
        re-draws all three panels.
        """
        records = self.history.records
        if len(records) < 2:
            return []

        now = time.time()
        times    = [r.timestamp - now for r in records]   # seconds relative to "now"
        raw      = [r.raw_rssi       for r in records]
        smoothed = [r.smoothed_rssi  for r in records]
        variances= [r.variance       for r in records]
        threshold= records[-1].threshold if records else 3.0
        statuses = [r.status         for r in records]

        # Map status enum → numeric for the status-band plot
        STATUS_NUM = {
            DetectionStatus.MOVEMENT:          2,
            DetectionStatus.INSUFFICIENT_DATA: 1,
            DetectionStatus.NO_MOVEMENT:       0,
        }
        status_nums = [STATUS_NUM[s] for s in statuses]

        # ── Update Panel 1 ─────────────────────────────────────────────────
        self.line_raw.set_data(times, raw)
        self.line_smoothed.set_data(times, smoothed)
        self.ax_rssi.relim()
        self.ax_rssi.autoscale_view()

        # ── Update Panel 2 ─────────────────────────────────────────────────
        self.line_var.set_data(times, variances)
        self.line_threshold.set_data([times[0], times[-1]], [threshold, threshold])
        self.ax_var.relim()
        self.ax_var.autoscale_view()
        # Ensure threshold is always visible even if variance is tiny
        var_max = max(max(variances, default=1.0), threshold * 1.5)
        self.ax_var.set_ylim(0, var_max * 1.1)

        # ── Update Panel 3 ─────────────────────────────────────────────────
        self.line_status.set_data(times, status_nums)

        # Colour the status line by latest status
        latest_status = statuses[-1]
        clr = {
            DetectionStatus.MOVEMENT:          COLOUR_MOVEMENT,
            DetectionStatus.NO_MOVEMENT:       COLOUR_NONE,
            DetectionStatus.INSUFFICIENT_DATA: COLOUR_PENDING,
        }[latest_status]
        self.line_status.set_color(clr)

        # ── Update header status text ──────────────────────────────────────
        self.status_text.set_text(f"●  {latest_status.value}")
        self.status_text.set_color(clr)

        return [self.line_raw, self.line_smoothed, self.line_var,
                self.line_threshold, self.line_status, self.status_text]

    def start(self) -> None:
        """
        Launch the animation loop. **Blocking** — calls plt.show() which
        blocks until the window is closed. Run in the main thread.
        """
        self._anim = FuncAnimation(
            self.fig,
            self._update,
            interval=self.interval_ms,
            blit=False,
            cache_frame_data=False,
        )
        plt.show()
