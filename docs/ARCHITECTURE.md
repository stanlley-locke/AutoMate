# AutoMate System Architecture

This document describes the architectural design and subsystems that power AutoMate.

---

## 1. Subsystem Architecture Overview

AutoMate combines edge perception, structured agent reasoning, and human-cadence input synthesis into a unified automation loop.

```
+-------------------------------------------------------------+
|                      User Interface                         |
|     CustomTkinter GUI Dashboard   /   Click Command CLI     |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                     AutoMate Agent Core                     |
|  - Task Decomposition & Goal Tracking                       |
|  - Perception-Reason-Action (PRA) Execution Loop            |
|  - Anti-Stuck State Watchdog                                |
+--------------+-------------------------------+--------------+
               |                               |
               v                               v
+-------------------------------+ +---------------------------+
|       Vision Perception       | |      AI Reasoning Core    |
| - DPI-Aware Screen Capture    | | - Cloudflare Workers AI   |
| - Multi-Monitor Detection     | |   (Llama-3.2-11b Vision)  |
| - Optimization & Compression  | | - Anthropic Claude API    |
+--------------+----------------+ +-------------+-------------+
               |                                |
               +---------------+----------------+
                               |
                               v
+-------------------------------------------------------------+
|                     Desktop Tool Suite                      |
|  - Application Lifecycle (Chrome, VS Code, Explorer, Apps)  |
|  - Media Operations (YouTube Play, Pause, Skip, Search)     |
|  - Filesystem Operations (Directories, Files, Manifests)    |
|  - Shell & PowerShell Command Execution                     |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                 Human-Grade Input Controller                |
|  - Non-Linear Bezier Curve Mouse Trajectories               |
|  - Variable Character-by-Character Typing Jitter            |
|  - Multi-Stage Reading Page Scrolling                       |
|  - Cooperative Pause & Contemplation Interrupter            |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                     Windows OS Safeguards                   |
|  - SetThreadExecutionState Keep-Awake Engine                |
|  - Screen Corner Emergency Failsafe (Top-Left)              |
|  - Coordinate Boundary Clamp & DPI Normalization            |
+-------------------------------------------------------------+
```

---

## 2. Core Components

### Perception Subsystem (`automate/screen.py`)
- Auto-detects physical screen resolution on Windows with per-monitor DPI awareness (`SetProcessDpiAwareness`).
- Captures unscaled high-resolution screen frames and resizes them proportionally for vision model analysis.

### Reasoning Engine (`automate/providers/`)
- **Cloudflare Workers AI (`cloudflare.py`):** Utilizes `@cf/meta/llama-3.2-11b-vision-instruct` on Cloudflare's serverless edge for fast, cost-effective vision reasoning without cloud rate limits.
- **Anthropic Claude (`anthropic_provider.py`):** Integrates Claude Sonnet via the Computer Use API for complex multi-app orchestration.

### Human-Grade Input Controller (`automate/human_input.py`)
- **Natural Mouse Movement:** Employs cubic Bezier curves with speed deceleration curves and micro-adjustments instead of instant teleports.
- **Natural Keyboard Typing:** Simulates character-by-character typing with Gaussian timing variance, longer pauses after punctuation, and spacebar rhythm.
- **Reading Scroll:** Employs multi-stage smooth scrolling with reading pauses and micro-reversals simulating human comprehension.

### Keep-Awake & System Safeguards (`automate/keep_awake.py`)
- Invokes the Windows Kernel32 API function `SetThreadExecutionState` with `ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED` to keep unattended 24/7 routines from sleeping.
- Monitors mouse coordinates: if the cursor moves to (0,0) (the top-left corner), the safety watchdog instantly aborts execution.
