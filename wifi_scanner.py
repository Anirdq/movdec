"""
WiFi Movement Detection System
================================
wifi_scanner.py — Module responsible for scanning nearby WiFi networks
and extracting RSSI values for a target SSID.

Supports both Windows (via pywifi) and Linux (via iwlist subprocess).
"""
from __future__ import annotations

import platform
import subprocess
import re
import sys
import time
import logging

logger = logging.getLogger(__name__)


def _scan_windows(target_ssid: str) -> float | None:
    """
    Scan WiFi networks on Windows using pywifi.

    Args:
        target_ssid: The SSID name to search for.

    Returns:
        RSSI value (dBm) as float, or None if not found.
    """
    try:
        import pywifi  # type: ignore
        from pywifi import const  # type: ignore
        import os, io

        wifi = pywifi.PyWiFi()
        iface = wifi.interfaces()[0]

        # Suppress pywifi's noisy "Open handle failed" stderr messages
        _old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            iface.scan()
            time.sleep(2)  # Allow time for scan results to populate
            results = iface.scan_results()
        finally:
            sys.stderr = _old_stderr  # Always restore stderr
        for profile in results:
            if profile.ssid.strip() == target_ssid.strip():
                # pywifi returns signal as dBm (negative integer)
                return float(profile.signal)

        logger.warning(f"SSID '{target_ssid}' not found in Windows scan results.")
        return None

    except ImportError:
        logger.error("pywifi is not installed. Run: pip install pywifi comtypes")
        raise
    except IndexError:
        logger.error("No WiFi interfaces found on this machine.")
        return None
    except Exception as e:
        logger.error(f"Windows WiFi scan failed: {e}")
        return None


def _scan_linux(target_ssid: str) -> float | None:
    """
    Scan WiFi networks on Linux using the 'iwlist' command-line tool.

    Args:
        target_ssid: The SSID name to search for.

    Returns:
        RSSI value (dBm) as float, or None if not found.
    """
    try:
        # Discover the wireless interface name (wlan0, wlp2s0, etc.)
        result = subprocess.run(
            ["iwconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        interfaces = re.findall(r"^(\S+)\s+IEEE 802\.11", result.stdout, re.MULTILINE)

        if not interfaces:
            logger.error("No wireless interface detected via iwconfig.")
            return None

        iface = interfaces[0]
        logger.debug(f"Using WiFi interface: {iface}")

        # Run iwlist scan on the detected interface
        scan_result = subprocess.run(
            ["sudo", "iwlist", iface, "scan"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Parse scan output — find cells matching our SSID
        # Split by "Cell" blocks for per-network parsing
        cells = scan_result.stdout.split("Cell ")
        for cell in cells[1:]:  # Skip the header
            ssid_match = re.search(r'ESSID:"(.+?)"', cell)
            signal_match = re.search(r"Signal level=(-\d+) dBm", cell)

            if ssid_match and signal_match:
                ssid = ssid_match.group(1)
                signal = float(signal_match.group(1))
                if ssid.strip() == target_ssid.strip():
                    return signal

        logger.warning(f"SSID '{target_ssid}' not found in Linux scan results.")
        return None

    except FileNotFoundError:
        logger.error("'iwlist' not found. Install wireless-tools: sudo apt install wireless-tools")
        return None
    except subprocess.TimeoutExpired:
        logger.error("iwlist scan timed out.")
        return None
    except Exception as e:
        logger.error(f"Linux WiFi scan failed: {e}")
        return None


def get_rssi(target_ssid: str) -> float | None:
    """
    Platform-aware entry point to retrieve the RSSI for a given SSID.

    Automatically selects the correct scan backend based on the OS.

    Args:
        target_ssid: The WiFi SSID to monitor.

    Returns:
        RSSI in dBm (typically -30 to -90), or None if unavailable.
    """
    os_name = platform.system()
    logger.debug(f"Running on OS: {os_name}")

    if os_name == "Windows":
        return _scan_windows(target_ssid)
    elif os_name == "Linux":
        return _scan_linux(target_ssid)
    else:
        logger.error(f"Unsupported OS: {os_name}. Only Windows and Linux are supported.")
        return None
