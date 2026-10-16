# AutoMate

AutoMate is an autonomous Windows desktop automation agent powered by Cloudflare Workers AI vision models and Anthropic Claude Computer Use.

AutoMate perceives the desktop screen through DPI-aware screen capture and autonomously coordinates mouse, keyboard, and application operations. It is designed for both discrete interactive tasks and unattended long-running or overnight workflows.

---

## Key Features

- **Cloudflare Workers AI Vision:** Edge-hosted vision perception using `@cf/meta/llama-3.2-11b-vision-instruct` for fast, cost-effective desktop reasoning.
- **Anthropic Claude Computer Use:** Alternative provider support for Claude Sonnet vision models.
- **Modern Desktop GUI:** Clean dashboard interface built with CustomTkinter featuring real-time telemetry, execution cards, prompt runner, predefined workflow cards, live console, and settings management.
- **Human-Grade Input Simulation:** Non-linear Bezier mouse paths, character-by-character typing with natural jitter and punctuation delays, and progressive multi-stage reading scroll.
- **Predefined Workflows:** Complete autonomous recipes for web browsing with YouTube streaming, VS Code Python development, and File Explorer organization.
- **Windows Sleep Prevention:** Native `SetThreadExecutionState` keep-awake engine preventing system sleep and display shutoff during unattended execution.
- **Safety Safeguards:** Instant emergency stop controls, top-left mouse corner failsafe, boundary clamping, and audit logging.
- **Standalone Installer:** Packaged as an installable Windows MSI package compiled via PyInstaller and WiX Toolset v7.0.

---

## Quick Start

### Installation

```powershell
# Clone repository
git clone https://github.com/stanlley-locke/AutoMate.git
cd AutoMate

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install package dependencies
pip install -r requirements.txt # or pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and provide your credentials:

```powershell
Copy-Item .env.example .env
```

```ini
PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id_here
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here
CLOUDFLARE_MODEL=@cf/meta/llama-3.2-11b-vision-instruct
```

### Running the Desktop GUI

```powershell
python -m automate ui
```

### Running Tasks via CLI

```powershell
# Run discrete prompt task
python -m automate run "Open Chrome and search for weather in Nairobi"

# Run with repetition and YouTube stream duration
python -m automate run "Search YouTube for ambient music" --repeat 3 --watch-mins 2.5

# Run a predefined workflow recipe
python -m automate recipe browse-weather-youtube
```

---

## Predefined Automation Workflows

AutoMate includes high-level human worker execution routines:

1. **browse-weather-youtube:** Searches weather in Google Chrome, queries Cloudflare AI for a dynamic YouTube topic, streams the video for 2-3 minutes with live progress updates, skips, toggles playback, scrolls with natural reading cadence, and gracefully closes tabs.
2. **code-python-project:** Launches Visual Studio Code, creates a new file, visually types Python code character-by-character, saves the file as `automate_script.py`, executes it in the integrated terminal, and closes.
3. **file-manager-organize:** Opens Windows File Explorer on Desktop, creates workspace directories and subdirectories using native shortcuts and typing, writes a manifest file, and gracefully closes Explorer.
4. **full-human-worker:** Chained master routine combining Web Browsing, Media Playback, File Organization, and VS Code Development with natural contemplation transitions.

---

## Standalone Windows Installer (.msi)

AutoMate can be compiled into a standalone Windows Installer package:

```powershell
# 1. Compile standalone executable with PyInstaller
python -m PyInstaller --noconfirm AutoMate.spec

# 2. Build MSI package with WiX Toolset v7.0
& "C:\Program Files\WiX Toolset v7.0\bin\wix.exe" build -arch x64 AutoMate.wxs -o "dist\AutoMate-Setup-v1.0.0.msi"
```

The resulting package (`dist/AutoMate-Setup-v1.0.0.msi`) bundles the complete application runtime, sets up Desktop and Start Menu shortcuts, registers the application icon, and supports standard Windows uninstallation.

---

## Documentation

Comprehensive documentation is available in the `docs/` folder:

- [Setup and Build Guide](docs/SETUP_AND_BUILD.md): Step-by-step instructions from environment setup to standalone binary compilation and MSI generation.
- [CLI Reference](docs/CLI_REFERENCE.md): Full command-line options, parameters, and usage examples.
- [System Architecture](docs/ARCHITECTURE.md): Technical architecture covering perception, reasoning models, human input simulation, and system safeguards.

---

## License

This project is licensed under the Apache 2.0 License.
