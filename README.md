# 🚗 SafeDash — Real-Time Driver Drowsiness Detection & Monitoring System

> An embedded AI system for real-time driver attention monitoring, built on NVIDIA Jetson Nano.  
> Developed at the **School of Computing and Electrical Engineering, IIT Mandi**.

📄 [Project Report](https://drive.google.com/drive/folders/1U4jq64dsoF5--_NPGIv1SxsrH9lrvMU_) · 🎥 [Demo Videos](https://drive.google.com/drive/folders/1U4jq64dsoF5--_NPGIv1SxsrH9lrvMU_) · 🔩 [CAD Files](https://github.com/SHRI-14/SAFEDASH/tree/main/CAD)

---

## Overview

SafeDash is a low-cost, non-invasive driver monitoring system that detects drowsiness and inattention in real time using a standard USB webcam and the MediaPipe face tracking pipeline running on an NVIDIA Jetson Nano. When unsafe behaviour is detected, a three-stage alert mechanism (visual → audio → haptic) progressively re-engages the driver. All data is streamed to a Flask + Redis web dashboard for live and historical analysis.

---

## Features

- **Real-time facial landmark tracking** — MediaPipe Face Mesh extracts 468 landmarks per frame at 30+ FPS on-device
- **Unified Attention Score (1–5)** — computed from eye closure (EAR), yawning (MAR), blink rate, and head pose
- **Three-stage alert system**
  - 🖥️ Stage 1 — Visual warning on integrated LCD
  - 🔊 Stage 2 — Voice alert via external speaker
  - 📳 Stage 3 — Haptic feedback via steering-mounted vibration motors
- **Web dashboard** — live attention score, blink rate, head orientation (yaw/pitch/roll), eye state, and historical charts
- **Automatic email alerts** — SMTP notification to supervisors when attention drops below threshold (15-second cooldown)
- **Redis time-series storage** — data auto-expires after 24 hours; supports multi-device fleet monitoring
- **Face-not-detected logic** — triggers haptic + audio alert if face is absent for >4 seconds
- **Custom acrylic enclosure** — SolidWorks-designed, laser-cut black acrylic housing with thermal management

---

## System Architecture

```
USB Webcam
    │
    ▼
MediaPipe Face Mesh (468 landmarks)
    │
    ├── Eye Aspect Ratio (EAR)   →  Eye closure / blink detection
    ├── Mouth Aspect Ratio (MAR) →  Yawn detection
    ├── Blink Rate (BR)          →  Sliding 5s window
    └── Head Pose (Yaw/Pitch/Roll)
    │
    ▼
Unified Attention Score (1–5)
    │
    ├── Alert Engine  →  LCD / Speaker / Haptic Motors
    └── Flask Backend →  Redis →  Web Dashboard + Email Alerts
```

---

## Hardware

| Component | Details |
|---|---|
| Processor | NVIDIA Jetson Nano 4GB |
| Camera | USB Webcam (RGB, 30–45 FPS) |
| Display | 3.2-inch HDMI LCD |
| Audio | External speaker via USB sound card |
| Haptic | 2× DC vibration motors (steering-mounted) via L298N driver |
| Connectivity | Intel AC8265 Wi-Fi module |
| Storage | 32 GB micro-SD |
| Power | 12V (actuators) / 5V (Jetson & logic) via automotive buck converters |
| Enclosure | 3mm black acrylic, laser-cut, SolidWorks design |

**Total BOM cost: ~₹12,000**

---

## Software Stack

- **Edge (Jetson):** Python, MediaPipe, OpenCV, Haarcascade (fallback detector)
- **Backend:** Flask, Redis
- **Frontend:** Chart.js (real-time graphs), HTML/CSS dashboard
- **Alerts:** SMTP email

---

## Repository Structure

```
SAFEDASH/
├── model.py                          # Attention scoring & drowsiness detection logic
├── stream_server.py                  # Flask backend + Redis + dashboard server
├── haarcascade_eye.py                # Haarcascade eye detector (fallback)
├── haarcascade_frontalface_default.py # Haarcascade face detector (fallback)
├── test_driver.py                    # Testing / simulation script
└── CAD/                              # SolidWorks enclosure design files
```

---

## Getting Started

### Prerequisites

- NVIDIA Jetson Nano with JetPack installed (or any Linux machine for testing)
- Python 3.8+
- Redis server
- USB webcam

### Installation

```bash
# Clone the repository
git clone https://github.com/SHRI-14/SAFEDASH.git
cd SAFEDASH

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install flask mediapipe opencv-python redis numpy
```

### Running

```bash
# Start Redis (in a separate terminal)
redis-server

# Start the stream server / dashboard
python3 stream_server.py
```

The dashboard will be available at **http://localhost:5001**

To run the drowsiness detection model on the Jetson:

```bash
python3 model.py
```

---

## Attention Scoring Algorithm

The system computes a normalized attention rating on a **1–5 scale**:

| Feature | Weight | Condition |
|---|---|---|
| Eye state (EAR) | 4 | Open = 1, Closed = 0 (threshold: EAR < 0.26) |
| Mouth state (MAR) | 2 | Closed = 1, Yawning = 0 (threshold: MAR > 0.40) |
| Head/Neck pose | 3 | 0–2 based on yaw/roll angles |
| Blink rate | 3 | Normal (1–3 blinks/s) = 1, else 0 |

**Raw score max = 15 → Normalized to 1–5 range**

Alert threshold: Score < 2

---

## Dashboard

The web dashboard supports:
- Live attention score with color-coded risk severity
- Real-time charts: attention score, blink frequency, head orientation (yaw/pitch/roll)
- Aggregated bar charts (1–60 min time ranges)
- Multi-device fleet monitoring via unique Jetson IDs
- Data refresh every 5 seconds

---

## Team

**School of Computing and Electrical Engineering, IIT Mandi**

| Name | Department |
|---|---|
| Navdeep Singh | PhD, Mechanical Engineering |
| Shriyaansh Gupta | B.Tech, Computer Science Engineering |
| Vansh Goel | B.Tech, Data Science and Engineering |
| Taneshq Gupta | B.Tech, Computer Science Engineering |
| Rohan Aggarwal | B.Tech, Data Science and Engineering |
| Navedhya Goyal | B.Tech, Mechanical Engineering |
| Ojas More | B.Tech, Electrical Engineering |
| Himanshi | B.Tech, Engineering Physics |

**Advisors:** Dr. Rohit Saluja, Dr. Gajendra Singh

---

## Acknowledgements

Thanks to the School of Computing and Electrical Engineering at IIT Mandi for providing laboratory facilities, equipment, and technical guidance throughout the project.

---

## License

This project was developed for academic purposes at IIT Mandi. Please contact the authors for usage permissions.
