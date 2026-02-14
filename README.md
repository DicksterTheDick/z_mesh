


> # 📡 Z-Mesh: Meshtastic File Transfer

**Z-Mesh** is a Python-based Terminal User Interface (TUI) designed for high-reliability file transfers over **Meshtastic** mesh networks. Unlike standard text messaging, Z-Mesh uses an automated chunking and acknowledgment (ACK) system to ensure files reach their destination even in high-latency or noisy radio environments.

The system provides a modern, interactive dashboard for monitoring nodes, selecting files, and tracking transfer progress in real-time.

## ✨ Features

-   **TUI Dashboard** — A sleek terminal interface powered by `Textual` with real-time logging and node discovery.
    
-   **Reliable Chunking** — Automatically splits files into 120-byte chunks to fit within LoRa packet limits while maintaining stability.
    
-   **Smart Retries & Watchdog** — Automatically detects timeouts and retries specific failed chunks up to 5 times.
    
-   **Progress Tracking** — Visual progress bars for both sending and receiving files.
    
-   **Node Discovery** — Automatically scans the mesh for active nodes and displays their Signal-to-Noise Ratio (SNR).
    
-   **Auto-Save** — Received files are automatically reconstructed and saved to your local `Downloads` folder.
    

## ⚙️ Installation & Setup

### 1. Prerequisites

You must have **Python 3.9+** and **Git** installed on your system.

If Git is not installed, install it using:

```
sudo apt install git -y

```

### 2. Project Setup

First, **clone the repository** from GitHub to your local machine:

```
git clone https://github.com/DicksterTheDick/z_mesh.git

```

Then, navigate into the project directory:

```
cd ~/z-mesh

```

### 3. Create a Python Virtual Environment

Running this script inside a virtual environment (`venv`) ensures that dependencies (like `meshtastic` and `textual`) do not conflict with your system packages.

```
python3 -m venv .venv

```

### 4. Activate the Virtual Environment

Activate it **every time** before running the app:

```
source .venv/bin/activate

```

### 5. Install Dependencies

With the virtual environment active, install the required packages:

```
pip install -r requirements.txt

```

### 6. Run Z-Mesh

1.  Connect your **Meshtastic device** via USB.
    
2.  Ensure the device is powered on and recognized by your OS.
    
3.  Run the application:
    

```
python3 z_mesh.py

```

## 🛠️ Configuration Note

The default settings are optimized for real-world reliability:

-   **Chunk Size:** 120 bytes (Optimized for LoRa overhead).
    
-   **Timeout:** 30 seconds (Allows for slow mesh hops).
    
-   **Max Retries:** 5 attempts per chunk.
