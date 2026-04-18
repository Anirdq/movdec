"""
WiFi Movement Detection System
================================
main.py — Entry point and orchestrator.

Wires together:
  - WiFi scanning (or demo simulation)
  - Signal smoothing and variance calculation
  - Movement detection and classification
  - Real-time terminal output
  - Live matplotlib dashboard

Usage:
    python main.py                   # Interactive — prompts for SSID
    python main.py --ssid "MyWiFi"   # Specify SSID directly
    python main.py --demo            # Run in demo/simulation mode (no WiFi needed)
    python main.py --help            # Show all options
"""

import argparse
import logging
import sys
import threading
import time

# ── Internal modules ──────────────────────────────────────────────────────────
from signal_processor import RingBuffer, MovingAverageFilter, VarianceCalculator
from movement_detector import MovementDetector, DetectionStatus
from visualizer import RealTimePlotter

# ── Constants / defaults ──────────────────────────────────────────────────────
DEFAULT_BUFFER_SIZE      = 100   # Maximum RSSI samples stored
DEFAULT_MA_WINDOW        = 5     # Moving-average window size (samples)
DEFAULT_VAR_WINDOW       = 10    # Variance sliding-window size (samples)
DEFAULT_VARIANCE_THRESHOLD = 3.0 # Variance above which movement is declared
DEFAULT_SCAN_INTERVAL    = 1.0   # Seconds between WiFi scans
DEFAULT_MIN_SAMPLES      = 5     # Minimum samples before classifying

# ── Terminal colour codes (ANSI) ──────────────────────────────────────────────
try:
    import colorama
    colorama.init(autoreset=True)
    C_RED    = "\033[91m"
    C_GREEN  = "\033[92m"
    C_YELLOW = "\033[93m"
    C_CYAN   = "\033[96m"
    C_BOLD   = "\033[1m"
    C_RESET  = "\033[0m"
except ImportError:
    # Graceful fallback if colorama is not installed
    C_RED = C_GREEN = C_YELLOW = C_CYAN = C_BOLD = C_RESET = ""


# ── Logging setup ─────────────────────────────────────────────────────────────

def setup_logging(verbose: bool) -> None:
    """Configure root logger based on verbosity flag."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── Terminal banner / header ───────────────────────────────────────────────────

def print_banner(ssid: str, demo: bool, threshold: float) -> None:
    """Print a styled startup banner to the terminal."""
    mode_str = f"{C_YELLOW}[DEMO MODE]{C_RESET}" if demo else f"{C_CYAN}[LIVE MODE]{C_RESET}"
    print(f"""
{C_BOLD}{'=' * 58}{C_RESET}
{C_BOLD}  [*]  WiFi Movement Detection System{C_RESET}
{'=' * 58}
  SSID      : {C_CYAN}{ssid}{C_RESET}
  Mode      : {mode_str}
  Threshold : {threshold} (variance)
{'-' * 58}
  Press {C_BOLD}Ctrl+C{C_RESET} to stop.
{'=' * 58}
""")


def print_status_line(result) -> None:
    """
    Print a single-line status update to the terminal for the latest reading.

    Overwrites the same line using carriage return for a clean rolling display.
    """
    ts    = time.strftime("%H:%M:%S", time.localtime(result.timestamp))
    rssi  = f"{result.raw_rssi:+.1f}"
    smth  = f"{result.smoothed_rssi:+.1f}"
    var   = f"{result.variance:.4f}"
    std   = f"{result.std_dev:.4f}"

    # Colour-code the status
    status_map = {
        DetectionStatus.MOVEMENT:          f"{C_RED}{C_BOLD}[!!] Movement Detected{C_RESET}",
        DetectionStatus.NO_MOVEMENT:       f"{C_GREEN}[OK] No Movement      {C_RESET}",
        DetectionStatus.INSUFFICIENT_DATA: f"{C_YELLOW}[..] Collecting Data  {C_RESET}",
    }
    status_str = status_map[result.status]

    line = (
        f"\r[{ts}]  "
        f"RSSI: {C_CYAN}{rssi}{C_RESET} dBm  "
        f"Smooth: {smth} dBm  "
        f"Var: {var}  "
        f"Std: {std}  "
        f"│  {status_str}"
    )
    # Write without newline so the line is overwritten on each tick
    sys.stdout.write(line)
    sys.stdout.flush()


# ── Data-collection worker ────────────────────────────────────────────────────

def collection_loop(
    ssid: str,
    demo: bool,
    scan_interval: float,
    buffer: RingBuffer,
    ma_filter: MovingAverageFilter,
    var_calc: VarianceCalculator,
    detector: MovementDetector,
    stop_event: threading.Event,
) -> None:
    """
    Background thread: continuously polls for RSSI values, processes them,
    classifies movement, and prints status to the terminal.

    Args:
        ssid          : Target WiFi SSID (ignored in demo mode).
        demo          : If True, use synthetic data from demo_mode module.
        scan_interval : Seconds between scans.
        buffer        : Shared RingBuffer for raw RSSI samples.
        ma_filter     : MovingAverageFilter instance.
        var_calc      : VarianceCalculator instance.
        detector      : MovementDetector instance.
        stop_event    : Threading event; set to True to terminate the loop.
    """
    if demo:
        from demo_mode import get_simulated_rssi as get_rssi_fn
    else:
        from wifi_scanner import get_rssi as _wifi_get_rssi

        def get_rssi_fn():  # type: ignore[misc]
            return _wifi_get_rssi(ssid)

    consecutive_failures = 0
    MAX_FAILURES = 5

    while not stop_event.is_set():
        loop_start = time.monotonic()

        # ── 1. Acquire RSSI ───────────────────────────────────────────────
        raw_rssi = get_rssi_fn()

        if raw_rssi is None:
            consecutive_failures += 1
            if consecutive_failures >= MAX_FAILURES:
                print(
                    f"\n{C_RED}[ERROR] Could not read RSSI for '{ssid}' "
                    f"after {MAX_FAILURES} attempts. "
                    f"Check SSID name or use --demo mode.{C_RESET}\n"
                )
                stop_event.set()
                break
            time.sleep(scan_interval)
            continue

        consecutive_failures = 0

        # ── 2. Store sample ───────────────────────────────────────────────
        buffer.append(raw_rssi)
        samples = buffer.get()

        # ── 3. Apply moving average ───────────────────────────────────────
        smoothed_rssi = ma_filter.apply(samples)

        # ── 4. Compute variance & std dev ─────────────────────────────────
        variance = var_calc.variance(samples)
        std_dev  = var_calc.std_dev(samples)

        # ── 5. Classify movement ──────────────────────────────────────────
        result = detector.classify(
            raw_rssi=raw_rssi,
            smoothed_rssi=smoothed_rssi,
            variance=variance,
            std_dev=std_dev,
            sample_count=len(samples),
        )

        # ── 6. Print to terminal ──────────────────────────────────────────
        print_status_line(result)

        # ── Maintain steady scan rate ─────────────────────────────────────
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, scan_interval - elapsed)
        time.sleep(sleep_time)

    print()  # Newline after the rolling status line


# ── Argument parser ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="movdec",
        description="WiFi-based human movement detection using RSSI fluctuation analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --demo
  python main.py --ssid "HomeNetwork" --threshold 2.5
  python main.py --ssid "OfficeWiFi" --interval 0.5 --verbose
        """,
    )

    parser.add_argument(
        "--ssid", "-s",
        type=str,
        default=None,
        help="WiFi SSID to monitor (e.g. 'MyHomeNetwork').",
    )
    parser.add_argument(
        "--demo", "-d",
        action="store_true",
        help="Run in demo/simulation mode (no WiFi hardware required).",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=DEFAULT_VARIANCE_THRESHOLD,
        help=f"Variance threshold for movement detection (default: {DEFAULT_VARIANCE_THRESHOLD}).",
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=DEFAULT_SCAN_INTERVAL,
        help=f"Seconds between WiFi scans (default: {DEFAULT_SCAN_INTERVAL}s).",
    )
    parser.add_argument(
        "--ma-window",
        type=int,
        default=DEFAULT_MA_WINDOW,
        help=f"Moving-average window size in samples (default: {DEFAULT_MA_WINDOW}).",
    )
    parser.add_argument(
        "--var-window",
        type=int,
        default=DEFAULT_VAR_WINDOW,
        help=f"Variance sliding-window size in samples (default: {DEFAULT_VAR_WINDOW}).",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=DEFAULT_BUFFER_SIZE,
        help=f"Total RSSI history buffer size (default: {DEFAULT_BUFFER_SIZE}).",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Disable the matplotlib dashboard (terminal output only).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    return parser.parse_args()


# ── Main entry point ───────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    # ── Resolve SSID ──────────────────────────────────────────────────────────
    if not args.demo and args.ssid is None:
        # Interactive prompt if SSID was not supplied as a flag
        print(f"\n{C_BOLD}WiFi Movement Detection System{C_RESET}")
        print("──────────────────────────────")
        args.ssid = input("  Enter target SSID (or press Enter for demo mode): ").strip()
        if not args.ssid:
            print(f"  {C_YELLOW}No SSID entered — switching to demo mode.{C_RESET}")
            args.demo = True
            args.ssid = "DEMO_SIMULATION"

    if args.demo and args.ssid is None:
        args.ssid = "DEMO_SIMULATION"

    # ── Initialise pipeline components ────────────────────────────────────────
    buffer   = RingBuffer(maxlen=args.buffer_size)
    ma_filter= MovingAverageFilter(window_size=args.ma_window)
    var_calc = VarianceCalculator(window_size=args.var_window)
    detector = MovementDetector(
        variance_threshold=args.threshold,
        min_samples=DEFAULT_MIN_SAMPLES,
    )

    print_banner(args.ssid, args.demo, args.threshold)

    # ── Start collection thread ───────────────────────────────────────────────
    stop_event = threading.Event()
    worker = threading.Thread(
        target=collection_loop,
        args=(
            args.ssid,
            args.demo,
            args.interval,
            buffer,
            ma_filter,
            var_calc,
            detector,
            stop_event,
        ),
        daemon=True,
        name="rssi-collector",
    )
    worker.start()

    # ── Launch visualiser (main thread) ───────────────────────────────────────
    if not args.no_plot:
        try:
            plotter = RealTimePlotter(
                history=detector.history,
                ssid=args.ssid,
                interval_ms=int(args.interval * 1000),
                window_seconds=60,
            )
            # plt.show() blocks until the window is closed
            plotter.start()
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
    else:
        # Terminal-only mode — block until Ctrl+C
        try:
            worker.join()
        except KeyboardInterrupt:
            print(f"\n\n{C_YELLOW}Stopping…{C_RESET}")
            stop_event.set()

    worker.join(timeout=3)
    print(f"\n{C_GREEN}Session ended. Goodbye!{C_RESET}\n")


if __name__ == "__main__":
    main()
