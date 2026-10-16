# AutoMate CLI Command Reference

This document provides a complete reference for all command-line operations, options, and parameters supported by AutoMate.

---

## Command Overview

```
automate [OPTIONS] COMMAND [ARGS]...
```

When run with no arguments, AutoMate automatically launches the modern graphical user interface.

### Global Options
- `--version`: Display version information and exit.
- `--help`: Display available commands and global options.

---

## Commands

### 1. `automate run [TASK]`
Execute an autonomous desktop automation instruction.

#### Arguments
- `TASK`: The natural language prompt instructing the agent what to perform.

#### Options
| Option | Short | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--provider` | `-p` | choice | `auto` | Vision provider: `cloudflare` or `anthropic`. |
| `--repeat` | `-r` | integer | `1` | Number of repetition cycles to execute. |
| `--duration` | `-d` | float | `0.0` | Maximum runtime in minutes (0 = unlimited). |
| `--hours` | | float | `0.0` | Hours to run unattended (0 = unlimited). |
| `--watch-mins` | | float | `2.5` | Minutes to watch/stream YouTube videos. |
| `--fast` / `--quick` | | flag | `false` | Enable fast mode with abbreviated pauses. |
| `--continuous` | | flag | `false` | Enable continuous autonomous execution mode. |
| `--keep-awake` / `--no-keep-awake` | | flag | `true` | Prevent Windows system sleep and screen turn-off. |
| `--max-steps` | | integer | `50` | Maximum discrete execution steps per cycle. |
| `--model` | | string | None | Override model identifier. |
| `--api-key` | | string | None | Override Anthropic API key. |
| `--cf-account-id` | | string | None | Override Cloudflare Account ID. |
| `--cf-token` | | string | None | Override Cloudflare API token. |
| `--cf-model` | | string | None | Override Cloudflare vision model identifier. |
| `--delay` | | float | `0.5` | Delay in seconds between physical input actions. |
| `--no-safety` | | flag | `false` | Disable safety boundary limits and failsafe corner. |
| `--verbose` | `-v` | flag | `false` | Enable detailed debug output. |

#### Examples
```powershell
# Open browser and search
automate run "Open Chrome and search for weather in Nairobi"

# Repeat YouTube ambient streaming task 3 times
automate run "Open Chrome and stream chill lofi beats on YouTube" --repeat 3 --watch-mins 3.0

# Run in fast execution mode
automate run "Open Notepad, write a meeting note, and save it" --fast
```

---

### 2. `automate recipe [NAME]`
Execute a predefined multi-step automation workflow.

#### Available Recipe Names
- `browse-weather-youtube`: Web browsing, weather search, dynamic Cloudflare topic search, 2-3 min YouTube stream, playback toggling, reading scroll, and tab closure.
- `code-python-project`: Launches Visual Studio Code, types complete Python code character-by-character, saves the file, executes in the terminal, and closes.
- `file-manager-organize`: Launches Windows File Explorer on Desktop, creates folders, subdirectories, writes a manifest note, and cleans up.
- `full-human-worker`: Chained master routine executing browsing, YouTube streaming, file organization, and VS Code development.

#### Options
| Option | Short | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--repeat` | `-r` | integer | `1` | Repetition cycles. |
| `--duration` | `-d` | float | `0.0` | Maximum runtime in minutes. |
| `--hours` | | float | `0.0` | Hours to run in hours. |
| `--watch-mins` | | float | `2.5` | YouTube stream watch duration in minutes. |
| `--fast` / `--quick` | | flag | `false` | Abbreviate pauses for testing. |

#### Example
```powershell
automate recipe full-human-worker --repeat 2
```

---

### 3. `automate recipes`
List all predefined automation recipes with descriptions and categories.

---

### 4. `automate ui`
Launch the AutoMate Windows Desktop GUI.

---

### 5. `automate config`
Inspect the active configuration settings, loaded environment variables, detected display resolution, and provider status.

---

### 6. `automate tools`
List all 30 built-in desktop automation tools, schemas, and parameter requirements.

---

### 7. `automate screenshot [OUTPUT_PATH]`
Capture an immediate full-screen desktop screenshot with DPI awareness.

---

### 8. `automate keep-awake`
Test and manually assert Windows sleep and display-off prevention.
