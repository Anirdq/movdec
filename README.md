# 📡 movdec — WiFi-Based Movement Detection System

A Python application that detects **human presence and movement** indoors by
analysing fluctuations in WiFi signal strength (RSSI).  
No special hardware is required — just a WiFi adapter and a nearby access point.

---

## How It Works

Human bodies absorb and reflect 2.4 / 5 GHz radio waves.  When someone moves
through a room, the **RSSI** (Received Signal Strength Indicator) received from
a nearby WiFi network fluctuates measurably.

The pipeline:

```
WiFi SSID scan ──► RingBuffer ──► Moving Average ──► Variance Calc ──► Threshold Classifier
                                                                              │
                                                                    "Movement Detected" / "No Movement"
```

| Stage | Detail |
|---|---|
| **Scan** | Reads RSSI (dBm) for the target SSID using `pywifi` (Windows) or `iwlist` (Linux) |
| **Buffer** | Stores the last N readings in a circular ring buffer |
| **Smooth** | Applies a simple moving average (SMA) to suppress noise spikes |
| **Variance** | Computes variance over a sliding window of smoothed samples |
| **Detect** | If `variance > threshold` → movement; else → no movement |
| **Visualise** | Live matplotlib dashboard + ANSI-coloured terminal output |

---

## Project Structure

```
movdec/
├── main.py              # Entry point — CLI, threading, orchestration
├── wifi_scanner.py      # Platform-aware WiFi RSSI acquisition
├── signal_processor.py  # RingBuffer, MovingAverageFilter, VarianceCalculator
├── movement_detector.py # Classification logic + DetectionHistory
├── visualizer.py        # Real-time matplotlib dashboard (3-panel dark theme)
├── demo_mode.py         # Synthetic RSSI generator (no WiFi hardware needed)
└── requirements.txt     # Python dependencies
```

---

## Installation

### 1. Clone / enter the project
```bash
git clone https://github.com/<you>/movdec.git
cd movdec
```

### 2. Create and activate a virtual environment (recommended)
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

> **Windows only:** `pywifi` additionally requires `comtypes` (included in
> `requirements.txt`).  Run your terminal / IDE **as Administrator** so that
> `pywifi` can trigger WiFi scans.

> **Linux only:** You need `wireless-tools`:  
> `sudo apt install wireless-tools`  
> And run the script with `sudo` (required for `iwlist scan`).

---

## Usage

### Quick-start (demo mode — no WiFi needed)
```bash
python main.py --demo
```

### Live mode with a specific SSID
```bash
python main.py --ssid "MyHomeNetwork"
```

### Interactive mode (prompts for SSID)
```bash
python main.py
```

### All options
```
usage: movdec [-h] [--ssid SSID] [--demo] [--threshold THRESHOLD]
              [--interval INTERVAL] [--ma-window MA_WINDOW]
              [--var-window VAR_WINDOW] [--buffer-size BUFFER_SIZE]
              [--no-plot] [--verbose]

options:
  --ssid, -s          WiFi SSID to monitor
  --demo, -d          Simulation mode (synthetic data, no hardware needed)
  --threshold, -t     Variance threshold for movement (default: 3.0)
  --interval, -i      Scan interval in seconds (default: 1.0)
  --ma-window         Moving-average window size in samples (default: 5)
  --var-window        Variance window size in samples (default: 10)
  --buffer-size       Total RSSI history size (default: 100)
  --no-plot           Terminal output only (no matplotlib window)
  --verbose, -v       Enable debug logging
```

### Tuning the threshold
| Environment | Suggested `--threshold` |
|---|---|
| Open room, short range to AP | `2.0 – 3.0` |
| Busy office / many walls | `4.0 – 6.0` |
| Very noisy environment | `8.0 – 12.0` |

---

## Example Terminal Output

```
══════════════════════════════════════════════════════════
  📡  WiFi Movement Detection System
══════════════════════════════════════════════════════════
  SSID      : HomeNetwork
  Mode      : 📡 LIVE MODE
  Threshold : 3.0 (variance)
──────────────────────────────────────────────────────────
  Press Ctrl+C to stop.
══════════════════════════════════════════════════════════

[20:14:01]  RSSI: -57.3 dBm  Smooth: -56.8 dBm  Var: 0.4200  Std: 0.6481  │  ✓  No Movement
[20:14:02]  RSSI: -61.1 dBm  Smooth: -58.2 dBm  Var: 3.9140  Std: 1.9784  │  ⚠  Movement Detected
[20:14:03]  RSSI: -63.4 dBm  Smooth: -59.7 dBm  Var: 8.2310  Std: 2.8690  │  ⚠  Movement Detected
[20:14:04]  RSSI: -55.8 dBm  Smooth: -58.1 dBm  Var: 1.1200  Std: 1.0583  │  ✓  No Movement
```

---

## Dashboard Screenshot

The live matplotlib dashboard opens automatically (use `--no-plot` to disable):

- **Panel 1 — RSSI Signal**: Raw (blue) vs smoothed moving-average (coral) in dBm  
- **Panel 2 — Variance**: Sliding-window variance (lavender) with red dashed threshold line  
- **Panel 3 — Status Band**: Green = No Movement | Red = Movement Detected | Amber = Collecting Data  

---

## Limitations & Notes

- **Scan rate**: WiFi scan APIs are typically limited to 1–2 scans per second on
  most platforms. Very fast movements may not be captured at low scan rates.
- **Windows Admin**: `pywifi` requires elevated privileges to trigger scans.
  Right-click the terminal → "Run as Administrator".
- **Linux `sudo`**: `iwlist scan` requires root. Run `sudo python main.py ...`.
- **Single AP**: Detection quality improves with closer proximity to the access
  point and fewer obstacles between monitor and AP.
- **Demo mode** uses a synthetic signal with 20-second cycles: 8 seconds of
  simulated movement followed by 12 seconds of quiet.

---

## Dependencies

| Library | Purpose |
|---|---|
| `numpy` | Variance, standard deviation, array operations |
| `matplotlib` | Real-time animated dashboard |
| `pywifi` | WiFi scanning on Windows |
| `comtypes` | COM interface layer required by pywifi on Windows |

---

## License

MIT — see [LICENSE](LICENSE).
