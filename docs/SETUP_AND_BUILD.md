# Setup and Build Guide for AutoMate

This document provides complete instructions for setting up the AutoMate desktop automation agent development environment from scratch, configuring credentials, running the CLI and GUI versions, bundling the standalone executable with PyInstaller, and producing a production Windows MSI installer via WiX Toolset v7.0.

---

## 1. Prerequisites and System Requirements

- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Python:** Python 3.10 through Python 3.14 (64-bit).
- **WiX Toolset:** WiX Toolset v7.0 (or v4/v5) installed on Windows for generating `.msi` installers.
- **Git:** Git for Windows.

---

## 2. Environment Setup

### Clone Repository
```powershell
git clone https://github.com/stanlley-locke/AutoMate.git
cd AutoMate
```

### Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1
```

### Install Dependencies
```powershell
# Upgrade pip and packaging tools
python -m pip install --upgrade pip setuptools wheel

# Install core runtime dependencies
pip install click pydantic pydantic-settings rich requests pillow pyautogui pynput pywinauto customtkinter darkdetect

# Install development and packaging tools
pip install pytest pyinstaller
```

---

## 3. Configuration (.env)

Create a `.env` file in the project root directory based on `.env.example`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` with your API credentials:

```ini
# Provider Selection: "cloudflare" (default) or "anthropic"
PROVIDER=cloudflare

# Cloudflare Workers AI Configuration
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id_here
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here
CLOUDFLARE_MODEL=@cf/meta/llama-3.2-11b-vision-instruct

# Anthropic Claude Configuration (Alternative Provider)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
MODEL=claude-sonnet-4-20250514

# Execution and Safety Settings
MAX_STEPS=50
ACTION_DELAY=0.5
SAFETY_MODE=true
KEEP_AWAKE=true
LOG_LEVEL=INFO
```

---

## 4. Running AutoMate

### Launch Graphical User Interface (GUI)
```powershell
# Run using the python module
python -m automate ui

# Or launch directly via entrypoint
python main_gui.py
```

### Run Autonomous Prompt Tasks (CLI)
```powershell
# Discrete single-cycle task
python -m automate run "Open Chrome and search for weather in Nairobi"

# Multiple repetitions with 2.5 min YouTube streaming
python -m automate run "Search YouTube for relaxing ambient music" --repeat 3 --watch-mins 2.5

# Fast mode (abbreviated pauses for rapid testing)
python -m automate run "Open Notepad and type a note" --fast
```

### Run Predefined Workflow Recipes (CLI)
```powershell
# List available recipes
python -m automate recipes

# Execute web browsing and YouTube routine
python -m automate recipe browse-weather-youtube

# Execute VS Code Python development routine
python -m automate recipe code-python-project

# Execute Windows File Explorer workspace organization
python -m automate recipe file-manager-organize

# Execute Full Human Worker master routine
python -m automate recipe full-human-worker
```

---

## 5. Compiling Standalone Executable (PyInstaller)

AutoMate uses a custom PyInstaller specification (`AutoMate.spec`) to bundle CustomTkinter assets, the Pillow imaging engine, PyAutoGUI, PyWinAuto, and the AutoMate library into a directory distribution.

### Build Executable
```powershell
python -m PyInstaller --noconfirm AutoMate.spec
```

The resulting distribution is generated in:
```
dist/AutoMate/
├── AutoMate.exe
└── _internal/
```

### Test Standalone Binary
```powershell
# Test CLI command engine
.\dist\AutoMate\AutoMate.exe --help

# Launch desktop GUI from compiled binary
.\dist\AutoMate\AutoMate.exe
```

---

## 6. Compiling Windows MSI Installer (WiX Toolset v7.0)

WiX Toolset packages the PyInstaller distribution, registers Start Menu and Desktop shortcuts, adds the high-resolution application icon, and creates standard Windows Add/Remove Programs uninstall entries.

### Accept WiX Toolset v7 OSMF EULA (One-Time Setup)
```powershell
& "C:\Program Files\WiX Toolset v7.0\bin\wix.exe" eula accept wix7
```

### Build MSI Package
```powershell
& "C:\Program Files\WiX Toolset v7.0\bin\wix.exe" build -arch x64 AutoMate.wxs -o "dist\AutoMate-Setup-v1.0.0.msi"
```

The completed Windows Installer will be available at:
```
dist/AutoMate-Setup-v1.0.0.msi
```

### Installing and Uninstalling the MSI
```powershell
# Install with basic progress UI
msiexec /i "dist\AutoMate-Setup-v1.0.0.msi" /qb

# Uninstall silently
msiexec /x "dist\AutoMate-Setup-v1.0.0.msi" /qn
```
