"""AutoMate Desktop Graphical User Interface.

A faithful, modern, high-productivity Windows Desktop application styled with the Quixotic emerald
card dashboard design system, tailored specifically for AutoMate's autonomous automation features:
- Outer soft neutral canvas background (#eaedf0 / #f3f5f8)
- Clean white top navigation bar with brand logo, pill-shaped tab menu, search, notification, and profile avatar
- Floating left capsule navigation panel with active green button and grouped icon clusters
- Header row with "Welcome Back, Stanley", active session range pill, and "+ Run Automation Task" button
- Automation-focused 3-Column Card Layout:
  * Column 1: AI Agent Engine Card (Cloudflare Workers AI / Claude Sonnet, 50 Max Steps, DPI Aware) +
              Execution Velocity Card (Dispatched Actions, Success Rate, Speedup Badge)
  * Column 2: Perception & Execution Pipeline Chart (6-stage pipeline: Perceive, Plan, Type, Stream, Code, Files
              with the emerald peak and floating pin bubble) + Organic Human Cadence indicator
  * Column 3: Desktop Automation Suite (30 Built-in Tools, Bezier mouse wave, Start Agent & Recipes buttons) +
              Safety Guard & Keep-Awake Card + 1-Click Instant Automation Workflow triggers
- Bottom Row: Recent Automation Tasks & Activity History table spanning across columns with Chrome, VS Code,
              File Explorer, and Master Routine records, status badges, and durations
- Dedicated fully-functional views for Dashboard, Task Runner, Predefined Workflows, Live Console, Settings,
  and Tools Catalog
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

from automate.config import Config, detect_screen_size, get_config
from automate.logger import DEFAULT_LOG_FILE, get_logger
from automate.recipes import (
    RECIPES,
    get_recipe,
    is_recipe_stopped,
    list_recipes,
    reset_recipe_stop,
    stop_recipe,
)
from automate.tools import DesktopToolSuite

logger = get_logger("automate.ui")

# Color Palette matching the emerald reference design
BG_APP = "#eaedf0"
CARD_BG = "#ffffff"
CARD_BORDER = "#e5e7eb"
ACCENT_GREEN = "#0d8a55"
ACCENT_GREEN_HOVER = "#097346"
ACCENT_MINT_BAR = "#86efac"
ACCENT_MINT_PILL = "#d1fae5"
ACCENT_MINT_TEXT = "#065f46"
TEXT_DARK = "#111827"
TEXT_GRAY = "#6b7280"
TEXT_LIGHT_GRAY = "#9ca3af"


class QueueLoggingHandler(logging.Handler):
    """Thread-safe logging handler routing log events to a UI queue."""

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_queue.put(("LOG", record.levelname, msg))
        except Exception:
            self.handleError(record)


class StdoutRedirector:
    """Redirects stdout writes to the UI log queue."""

    def __init__(self, log_queue: queue.Queue, prefix: str = "") -> None:
        self.log_queue = log_queue
        self.prefix = prefix
        self._orig = sys.stdout

    def write(self, text: str) -> None:
        if self._orig:
            try:
                self._orig.write(text)
            except Exception:
                pass
        cleaned = text.strip()
        if cleaned:
            self.log_queue.put(("OUTPUT", "INFO", f"{self.prefix}{cleaned}"))

    def flush(self) -> None:
        if self._orig:
            try:
                self._orig.flush()
            except Exception:
                pass


class AutoMateApp(ctk.CTk):
    """Main AutoMate Desktop GUI Application."""

    def __init__(self) -> None:
        super().__init__()

        # Window configuration
        self.title("AutoMate | Desktop Automation Agent")
        self.geometry("1280x840")
        self.minsize(1100, 720)
        self.configure(fg_color=BG_APP)

        # Light theme default matching reference design
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("green")

        # Set window icon if exists
        icon_path = Path("automate_icon.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path.resolve()))
            except Exception:
                pass

        # Application state
        self.log_queue: queue.Queue = queue.Queue()
        self.current_thread: Optional[threading.Thread] = None
        self.is_running: bool = False
        self.active_agent = None
        self.start_time: float = 0.0

        # Load configuration
        try:
            self.cfg = get_config()
        except Exception:
            self.cfg = Config()

        # Connect logging to UI queue
        self._setup_logging_bridge()

        # Main Layout:
        # Row 0: Top Navbar (full width)
        # Row 1: Body area (Left: Floating Capsule Panel, Right: Scrollable Content)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Build Top Navbar
        self._build_top_navbar()

        # Build Body Container
        self.body_container = ctk.CTkFrame(self, fg_color="transparent")
        self.body_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(12, 20))
        self.body_container.grid_rowconfigure(0, weight=1)
        self.body_container.grid_columnconfigure(0, weight=0)  # Left Capsule
        self.body_container.grid_columnconfigure(1, weight=1)  # Main View Area

        # Build Floating Left Capsule
        self._build_floating_capsule()

        # Build Main View Container
        self.view_container = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.view_container.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        self.view_container.grid_rowconfigure(0, weight=1)
        self.view_container.grid_columnconfigure(0, weight=1)

        # Build View Frames
        self.views: Dict[str, ctk.CTkFrame] = {
            "dashboard": self._build_dashboard_view(),
            "runner": self._build_runner_view(),
            "recipes": self._build_recipes_view(),
            "console": self._build_console_view(),
            "settings": self._build_settings_view(),
            "tools": self._build_tools_view(),
        }

        # Start with Dashboard view
        self.switch_view("dashboard")

        # Start periodic log queue polling
        self.after(100, self._process_log_queue)

    def _setup_logging_bridge(self) -> None:
        """Route logger events to the UI queue."""
        q_handler = QueueLoggingHandler(self.log_queue)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        q_handler.setFormatter(formatter)
        q_handler.setLevel(logging.INFO)

        for log_name in ["automate", "automate.actions", "automate.recipes", "automate.tools", "automate.agent"]:
            l = logging.getLogger(log_name)
            l.addHandler(q_handler)
            l.setLevel(logging.INFO)

        sys.stdout = StdoutRedirector(self.log_queue)  # type: ignore

    # -------------------------------------------------------------------------
    # 1. Top Navbar
    # -------------------------------------------------------------------------
    def _build_top_navbar(self) -> None:
        """Create the clean white top navbar with pill-shaped tabs, search, and avatar."""
        self.navbar_card = ctk.CTkFrame(
            self,
            height=62,
            fg_color=CARD_BG,
            corner_radius=22,
            border_width=1,
            border_color=CARD_BORDER,
        )
        self.navbar_card.grid(row=0, column=0, padx=20, pady=(16, 0), sticky="ew")
        self.navbar_card.grid_columnconfigure(1, weight=1)

        # Left: Logo & Brand Name
        brand_frame = ctk.CTkFrame(self.navbar_card, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        logo_btn = ctk.CTkButton(
            brand_frame,
            text="A",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            width=36,
            height=36,
            corner_radius=18,
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            text_color="#ffffff",
            command=lambda: self.switch_view("dashboard"),
        )
        logo_btn.pack(side="left", padx=(0, 8))

        brand_lbl = ctk.CTkLabel(
            brand_frame,
            text="AutoMate",
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=TEXT_DARK,
        )
        brand_lbl.pack(side="left")

        # Center: Pill-shaped Tab Menu
        menu_capsule = ctk.CTkFrame(self.navbar_card, fg_color="#f1f5f9", corner_radius=20, height=42)
        menu_capsule.grid(row=0, column=1, padx=10, pady=8)

        self.pill_buttons: Dict[str, ctk.CTkButton] = {}
        tab_list = [
            ("dashboard", "Dashboard"),
            ("runner", "Task Runner"),
            ("recipes", "Workflows"),
            ("console", "Live Console"),
            ("settings", "Settings"),
            ("tools", "Tools"),
        ]

        for v_id, label in tab_list:
            btn = ctk.CTkButton(
                menu_capsule,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
                fg_color="transparent",
                text_color=TEXT_GRAY,
                hover_color="#e2e8f0",
                corner_radius=16,
                height=32,
                command=lambda key=v_id: self.switch_view(key),
            )
            btn.pack(side="left", padx=3, pady=4)
            self.pill_buttons[v_id] = btn

        # Right: Search Icon, Bell Icon, Avatar Profile
        right_frame = ctk.CTkFrame(self.navbar_card, fg_color="transparent")
        right_frame.grid(row=0, column=2, padx=20, pady=10, sticky="e")

        search_btn = ctk.CTkButton(
            right_frame,
            text="🔍",
            font=ctk.CTkFont(size=12),
            width=36,
            height=36,
            corner_radius=18,
            fg_color="#f1f5f9",
            hover_color="#e2e8f0",
            text_color=TEXT_GRAY,
            command=lambda: self.switch_view("tools"),
        )
        search_btn.pack(side="left", padx=4)

        bell_btn = ctk.CTkButton(
            right_frame,
            text="🔔",
            font=ctk.CTkFont(size=12),
            width=36,
            height=36,
            corner_radius=18,
            fg_color="#f1f5f9",
            hover_color="#e2e8f0",
            text_color=TEXT_GRAY,
            command=lambda: self.switch_view("console"),
        )
        bell_btn.pack(side="left", padx=4)

        avatar_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        avatar_frame.pack(side="left", padx=(8, 0))

        avatar_btn = ctk.CTkButton(
            avatar_frame,
            text="S",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            width=36,
            height=36,
            corner_radius=18,
            fg_color="#0f172a",
            hover_color="#334155",
            text_color="#ffffff",
            command=lambda: self.switch_view("settings"),
        )
        avatar_btn.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(avatar_frame, text="⌄", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(side="left")

    # -------------------------------------------------------------------------
    # 2. Floating Left Capsule
    # -------------------------------------------------------------------------
    def _build_floating_capsule(self) -> None:
        """Create the compact floating left capsule sidepanel matching reference design."""
        self.capsule_card = ctk.CTkFrame(
            self.body_container,
            width=58,
            fg_color=CARD_BG,
            corner_radius=28,
            border_width=1,
            border_color=CARD_BORDER,
        )
        self.capsule_card.grid(row=0, column=0, sticky="ns", padx=(0, 6), pady=0)
        self.capsule_card.pack_propagate(False)

        # Top Button: Green active 4-dots grid button
        self.cap_top_btn = ctk.CTkButton(
            self.capsule_card,
            text="⊞",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=40,
            height=40,
            corner_radius=14,
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            text_color="#ffffff",
            command=lambda: self.switch_view("dashboard"),
        )
        self.cap_top_btn.pack(pady=(16, 12))

        # Cluster 1: 3 icons (Dashboard, Runner, Workflows)
        c1 = ctk.CTkFrame(self.capsule_card, fg_color="transparent")
        c1.pack(pady=4)

        self.cap_icons: Dict[str, ctk.CTkButton] = {}

        btn_chart = self._create_capsule_icon(c1, "📊", lambda: self.switch_view("dashboard"))
        btn_run = self._create_capsule_icon(c1, "⚡", lambda: self.switch_view("runner"))
        btn_work = self._create_capsule_icon(c1, "📋", lambda: self.switch_view("recipes"))
        self.cap_icons["dashboard"] = btn_chart
        self.cap_icons["runner"] = btn_run
        self.cap_icons["recipes"] = btn_work

        # Divider line
        div = ctk.CTkFrame(self.capsule_card, height=1, width=28, fg_color="#e5e7eb")
        div.pack(pady=10)

        # Cluster 2: 3 icons (Console, Timer/Activity, Tools)
        c2 = ctk.CTkFrame(self.capsule_card, fg_color="transparent")
        c2.pack(pady=4)

        btn_con = self._create_capsule_icon(c2, "🖥", lambda: self.switch_view("console"))
        btn_time = self._create_capsule_icon(c2, "⏱", lambda: self.switch_view("dashboard"))
        btn_tools = self._create_capsule_icon(c2, "🧰", lambda: self.switch_view("tools"))
        self.cap_icons["console"] = btn_con
        self.cap_icons["tools"] = btn_tools

        # Spacer to push bottom icons down
        spacer = ctk.CTkFrame(self.capsule_card, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Bottom Cluster: Settings + Emergency Stop
        c_bot = ctk.CTkFrame(self.capsule_card, fg_color="transparent")
        c_bot.pack(pady=(0, 16))

        btn_set = self._create_capsule_icon(c_bot, "⚙", lambda: self.switch_view("settings"))
        self.cap_icons["settings"] = btn_set

        # Emergency Stop icon (soft red)
        stop_btn = ctk.CTkButton(
            c_bot,
            text="⏹",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=36,
            height=36,
            corner_radius=12,
            fg_color="#fee2e2",
            hover_color="#fca5a5",
            text_color="#ef4444",
            command=self.emergency_stop,
        )
        stop_btn.pack(pady=4)

    def _create_capsule_icon(self, parent: ctk.CTkFrame, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent,
            text=text,
            font=ctk.CTkFont(size=15),
            width=36,
            height=36,
            corner_radius=12,
            fg_color="transparent",
            hover_color="#f1f5f9",
            text_color=TEXT_GRAY,
            command=command,
        )
        btn.pack(pady=3)
        return btn

    def switch_view(self, name: str) -> None:
        """Switch active view and update tab pills and capsule state."""
        for v_id, frame in self.views.items():
            if v_id == name:
                frame.grid(row=0, column=0, sticky="nsew")
                if v_id in self.pill_buttons:
                    self.pill_buttons[v_id].configure(fg_color="#ffffff", text_color=TEXT_DARK, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
                if v_id in self.cap_icons:
                    self.cap_icons[v_id].configure(fg_color="#f1f5f9", text_color=ACCENT_GREEN)
            else:
                frame.grid_forget()
                if v_id in self.pill_buttons:
                    self.pill_buttons[v_id].configure(fg_color="transparent", text_color=TEXT_GRAY, font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"))
                if v_id in self.cap_icons:
                    self.cap_icons[v_id].configure(fg_color="transparent", text_color=TEXT_GRAY)

    # -------------------------------------------------------------------------
    # 3. Automation-Focused Dashboard View (Matching Reference Layout & Style)
    # -------------------------------------------------------------------------
    def _build_dashboard_view(self) -> ctk.CTkFrame:
        """Build the rich Automation Dashboard with tasks, cards, and execution metrics."""
        frame = ctk.CTkScrollableFrame(self.view_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # 1. Header Greeting Row
        greet_row = ctk.CTkFrame(frame, fg_color="transparent")
        greet_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        greet_row.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(greet_row, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="Welcome Back, ",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="normal"),
            text_color=TEXT_DARK,
        ).pack(side="left")

        ctk.CTkLabel(
            title_box,
            text="Stanley",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=TEXT_DARK,
        ).pack(side="left")

        # Right side date range pill and "+ Run Automation Task" button
        act_box = ctk.CTkFrame(greet_row, fg_color="transparent")
        act_box.grid(row=0, column=1, sticky="e")

        screen_w, screen_h = detect_screen_size()
        date_pill = ctk.CTkLabel(
            act_box,
            text=f"🖥  {screen_w}x{screen_h} DPI Ready  |  Active Session: Realtime   ⌄",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_DARK,
            fg_color=CARD_BG,
            corner_radius=12,
            padx=14,
            pady=7,
        )
        date_pill.pack(side="left", padx=8)

        add_btn = ctk.CTkButton(
            act_box,
            text="+ Run Automation Task",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            text_color="#ffffff",
            corner_radius=12,
            height=34,
            command=lambda: self.switch_view("runner"),
        )
        add_btn.pack(side="left")

        # 2. Main 3-Column Card Layout
        grid_3 = ctk.CTkFrame(frame, fg_color="transparent")
        grid_3.grid(row=1, column=0, sticky="ew")
        grid_3.grid_columnconfigure(0, weight=3)  # Left (AI Engine Card + Ops Velocity)
        grid_3.grid_columnconfigure(1, weight=4)  # Center (Pipeline Perception Chart)
        grid_3.grid_columnconfigure(2, weight=3)  # Right (30 Tools + Failsafe + 1-Click Workflows)

        # =====================================================================
        # COLUMN 1: Active AI Agent Engine Card & Execution Velocity
        # =====================================================================
        col1 = ctk.CTkFrame(grid_3, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # Outer Card
        c1_card = ctk.CTkFrame(col1, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        c1_card.pack(fill="x", pady=(0, 10))

        c1_h = ctk.CTkFrame(c1_card, fg_color="transparent")
        c1_h.pack(fill="x", padx=16, pady=(14, 2))
        ctk.CTkLabel(c1_h, text="AI Agent Engine", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(c1_h, text="↗", font=ctk.CTkFont(size=13), text_color=TEXT_LIGHT_GRAY).pack(side="right")
        ctk.CTkLabel(c1_card, text="Vision reasoning & perception pipeline", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_GRAY).pack(anchor="w", padx=16)

        # The Vibrant Emerald Green Engine Card
        engine_card = ctk.CTkFrame(c1_card, fg_color=ACCENT_GREEN, corner_radius=16, height=138)
        engine_card.pack(fill="x", padx=14, pady=12)
        engine_card.pack_propagate(False)

        prov_name = getattr(self.cfg, "provider", "cloudflare").upper()
        v_top = ctk.CTkFrame(engine_card, fg_color="transparent")
        v_top.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(v_top, text=f"{prov_name} WORKERS AI", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#ffffff").pack(side="left")
        ctk.CTkLabel(v_top, text="⚡", font=ctk.CTkFont(size=14, weight="bold"), text_color="#a7f3d0").pack(side="right")

        model_short = getattr(self.cfg, "cloudflare_model", "@cf/meta/llama-3.2-11b").split("/")[-1]
        ctk.CTkLabel(engine_card, text=f"Model: {model_short}", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#a7f3d0").pack(anchor="w", padx=16, pady=(2, 0))
        ctk.CTkLabel(engine_card, text="50 Max Steps", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#ffffff").pack(anchor="w", padx=16, pady=(2, 6))

        v_bot = ctk.CTkFrame(engine_card, fg_color="transparent")
        v_bot.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(v_bot, text="LATENCY 420ms", font=ctk.CTkFont(family="Consolas", size=10), text_color="#a7f3d0").pack(side="left")
        ctk.CTkLabel(v_bot, text="● ONLINE & READY", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#ffffff").pack(side="right")

        # Sub-Card: Execution Velocity
        rev_card = ctk.CTkFrame(col1, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        rev_card.pack(fill="x", pady=0)

        ctk.CTkLabel(rev_card, text="Execution Velocity", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_GRAY).pack(anchor="w", padx=16, pady=(12, 2))

        rev_b = ctk.CTkFrame(rev_card, fg_color="transparent")
        rev_b.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(rev_b, text="1,420 Ops Dispatched", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color=TEXT_DARK).pack(side="left")

        rev_badge = ctk.CTkLabel(
            rev_b,
            text="+12.8% Speed",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=ACCENT_MINT_TEXT,
            fg_color=ACCENT_MINT_PILL,
            corner_radius=10,
            padx=8,
            pady=3,
        )
        rev_badge.pack(side="right")

        # =====================================================================
        # COLUMN 2: Task Execution & Perception Pipeline Chart
        # =====================================================================
        col2 = ctk.CTkFrame(grid_3, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        col2.grid(row=0, column=1, sticky="nsew", padx=6)

        c2_h = ctk.CTkFrame(col2, fg_color="transparent")
        c2_h.pack(fill="x", padx=16, pady=(14, 4))

        # Title
        c2_title_box = ctk.CTkFrame(c2_h, fg_color="transparent")
        c2_title_box.pack(side="left")

        ctk.CTkLabel(c2_title_box, text="📊", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(c2_title_box, text="Perception & Action Pipeline", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=TEXT_DARK).pack(side="left")

        # Switcher pills: [ Realtime ] [ History (Active Green) ]
        switch_capsule = ctk.CTkFrame(c2_h, fg_color="#f1f5f9", corner_radius=14, height=28)
        switch_capsule.pack(side="right")

        ctk.CTkLabel(switch_capsule, text="Realtime", font=ctk.CTkFont(size=10), text_color=TEXT_GRAY, padx=8).pack(side="left")
        ann_pill = ctk.CTkLabel(switch_capsule, text="Pipeline", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ffffff", fg_color=ACCENT_GREEN, corner_radius=12, padx=10, pady=2)
        ann_pill.pack(side="left", padx=2, pady=2)

        ctk.CTkLabel(c2_h, text="↗", font=ctk.CTkFont(size=13), text_color=TEXT_LIGHT_GRAY).pack(side="right", padx=(0, 8))

        # Canvas for the 6 Rounded Bars Chart representing the perception & execution pipeline
        self.chart_canvas = tk.Canvas(col2, width=390, height=210, bg="#ffffff", highlightthickness=0)
        self.chart_canvas.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._draw_pipeline_chart(self.chart_canvas)

        # =====================================================================
        # COLUMN 3: Right Column (30 Tools, Failsafe Safety, 1-Click Workflows)
        # =====================================================================
        col3 = ctk.CTkFrame(grid_3, fg_color="transparent")
        col3.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        # Card 3A: 30 Tools & Bezier Mouse Wave
        c3_card = ctk.CTkFrame(col3, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        c3_card.pack(fill="x", pady=(0, 10))

        c3_h = ctk.CTkFrame(c3_card, fg_color="transparent")
        c3_h.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkLabel(c3_h, text="Automation Suite", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(c3_h, text="↗", font=ctk.CTkFont(size=12), text_color=TEXT_LIGHT_GRAY).pack(side="right")
        ctk.CTkLabel(c3_card, text="Integrated desktop operations", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_GRAY).pack(anchor="w", padx=16)

        ctk.CTkLabel(c3_card, text="Total Active Tools", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=TEXT_GRAY).pack(anchor="center", pady=(6, 0))
        ctk.CTkLabel(c3_card, text="30 Tools Ready", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color=TEXT_DARK).pack(anchor="center", pady=(0, 4))

        # Wave Canvas representing natural bezier mouse path
        self.wave_canvas = tk.Canvas(c3_card, width=220, height=45, bg="#ffffff", highlightthickness=0)
        self.wave_canvas.pack(fill="x", padx=16, pady=2)
        self._draw_wave_chart(self.wave_canvas)

        # Quick Action buttons: Start Agent / Workflows
        btn_box = ctk.CTkFrame(c3_card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(6, 14))

        send_btn = ctk.CTkButton(
            btn_box,
            text="▶ Start Agent",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            corner_radius=12,
            height=30,
            command=lambda: self.switch_view("runner"),
        )
        send_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        recv_btn = ctk.CTkButton(
            btn_box,
            text="📋 Recipes",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color=CARD_BG,
            hover_color="#f1f5f9",
            text_color=TEXT_DARK,
            border_width=1,
            border_color=CARD_BORDER,
            corner_radius=12,
            height=30,
            command=lambda: self.switch_view("recipes"),
        )
        recv_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # Card 3B: Safety Guard & Keep-Awake Card
        cred_card = ctk.CTkFrame(col3, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        cred_card.pack(fill="x", pady=(0, 10))

        cr_top = ctk.CTkFrame(cred_card, fg_color="transparent")
        cr_top.pack(fill="x", padx=16, pady=(10, 2))
        ctk.CTkLabel(cr_top, text="🛡", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(cr_top, text="Safety Guard & Keep-Awake", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(cred_card, text="Failsafe: Top-Left Corner | Sleep Prevention", font=ctk.CTkFont(size=9), text_color=TEXT_GRAY).pack(anchor="w", padx=16)

        cr_b = ctk.CTkFrame(cred_card, fg_color="transparent")
        cr_b.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(cr_b, text="100% Protected", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        cr_pill = ctk.CTkLabel(cr_b, text="ACTIVE", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=ACCENT_MINT_TEXT, fg_color=ACCENT_MINT_PILL, corner_radius=10, padx=8, pady=2)
        cr_pill.pack(side="right")

        # Card 3C: 1-Click Instant Automation Workflow Triggers
        mand_card = ctk.CTkFrame(col3, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        mand_card.pack(fill="x", pady=0)

        m_top = ctk.CTkFrame(mand_card, fg_color="transparent")
        m_top.pack(fill="x", padx=16, pady=(10, 2))
        ctk.CTkLabel(m_top, text="1-Click Workflows", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(m_top, text="↗", font=ctk.CTkFont(size=11), text_color=TEXT_LIGHT_GRAY).pack(side="right")
        ctk.CTkLabel(mand_card, text="Direct routine execution triggers", font=ctk.CTkFont(size=9), text_color=TEXT_GRAY).pack(anchor="w", padx=16)

        av_row = ctk.CTkFrame(mand_card, fg_color="transparent")
        av_row.pack(fill="x", padx=16, pady=(6, 12))

        wf_chips = [
            ("🌐", "browse-weather-youtube", "YouTube"),
            ("💻", "code-python-project", "VSCode"),
            ("📁", "file-manager-organize", "Files"),
            ("🤖", "full-human-worker", "Master"),
        ]

        for icon_txt, r_id, label_txt in wf_chips:
            chip_btn = ctk.CTkButton(
                av_row,
                text=icon_txt,
                font=ctk.CTkFont(size=12),
                width=32,
                height=32,
                corner_radius=16,
                fg_color="#f1f5f9",
                hover_color="#e2e8f0",
                command=lambda r_name=r_id: self.start_recipe_task(r_name),
            )
            chip_btn.pack(side="left", padx=3)

        plus2 = ctk.CTkLabel(
            av_row,
            text="+4",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            width=32,
            height=32,
            corner_radius=16,
            fg_color=ACCENT_GREEN,
            text_color="#ffffff",
        )
        plus2.pack(side="left", padx=3)

        # =====================================================================
        # ROW 3: Recent Automation Tasks & Activity History Table
        # =====================================================================
        hist_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        hist_card.grid(row=2, column=0, sticky="ew", pady=(12, 16))

        h_top = ctk.CTkFrame(hist_card, fg_color="transparent")
        h_top.pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(h_top, text="Recent Automated Tasks & Activity Log", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=TEXT_DARK).pack(side="left")
        ctk.CTkLabel(h_top, text="View Console ↗", font=ctk.CTkFont(size=12), text_color=ACCENT_GREEN).pack(side="right")
        ctk.CTkLabel(hist_card, text="Execution records and visual desktop interactions", font=ctk.CTkFont(size=10), text_color=TEXT_GRAY).pack(anchor="w", padx=18)

        # Table Header
        th = ctk.CTkFrame(hist_card, fg_color="transparent")
        th.pack(fill="x", padx=18, pady=(10, 4))
        th.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        th_labels = ["Target Application", "Executed Routine / Prompt", "Perception Mode", "Status", "Duration"]
        for i_col, h_text in enumerate(th_labels):
            ctk.CTkLabel(th, text=h_text, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_LIGHT_GRAY, anchor="w").grid(row=0, column=i_col, sticky="w", padx=6)

        # Table Rows
        rows_data = [
            ("🌐", "Google Chrome", "Weather Search & YouTube Ambient Stream", "Vision + Human Cadence", "● Successful", "2m 45s"),
            ("💻", "VS Code Editor", "Python Script Authoring & Terminal Run", "Character-by-character Typing", "● Successful", "48.2s"),
            ("📁", "File Explorer", "Desktop Workspace Organizer & Manifest", "Native Shortcuts + Verification", "● Successful", "19.4s"),
            ("🤖", "Master Routine", "End-to-End Autonomous Worker Cycle", "Multi-stage Continuous Pipeline", "● Successful", "5m 12s"),
        ]

        for r_icon, r_app, r_task, r_mode, r_stat, r_dur in rows_data:
            rf = ctk.CTkFrame(hist_card, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=4)
            rf.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

            # Name with icon
            col0 = ctk.CTkFrame(rf, fg_color="transparent")
            col0.grid(row=0, column=0, sticky="w", padx=6)

            ico_badge = ctk.CTkLabel(col0, text=r_icon, font=ctk.CTkFont(size=12), width=28, height=28, corner_radius=14, fg_color="#f1f5f9")
            ico_badge.pack(side="left", padx=(0, 8))

            name_box = ctk.CTkFrame(col0, fg_color="transparent")
            name_box.pack(side="left")
            ctk.CTkLabel(name_box, text=r_app, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=TEXT_DARK).pack(anchor="w")
            ctk.CTkLabel(name_box, text="Windows 11 Native", font=ctk.CTkFont(size=9), text_color=TEXT_GRAY).pack(anchor="w")

            # Routine
            ctk.CTkLabel(rf, text=r_task, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_DARK, anchor="w").grid(row=0, column=1, sticky="w", padx=6)

            # Mode
            ctk.CTkLabel(rf, text=r_mode, font=ctk.CTkFont(family="Segoe UI", size=11), text_color=TEXT_GRAY, anchor="w").grid(row=0, column=2, sticky="w", padx=6)

            # Status with green dot
            stat_lbl = ctk.CTkLabel(rf, text=r_stat, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=ACCENT_GREEN, anchor="w")
            stat_lbl.grid(row=0, column=3, sticky="w", padx=6)

            # Duration
            ctk.CTkLabel(rf, text=r_dur, font=ctk.CTkFont(family="Consolas", size=11), text_color=TEXT_DARK, anchor="w").grid(row=0, column=4, sticky="w", padx=6)

        ctk.CTkFrame(hist_card, fg_color="transparent", height=10).pack()

        return frame

    def _draw_pipeline_chart(self, canvas: tk.Canvas) -> None:
        """Draw the 6-stage automation pipeline chart with the highlighted peak bar."""
        w, h = 390, 210
        canvas.delete("all")

        # Dashed horizontal grid lines (5k, 4k, 3k, 2k, 1k, 0)
        y_levels = [
            (25, "5k"),
            (55, "4k"),
            (85, "3k"),
            (115, "2k"),
            (145, "1k"),
            (175, "0"),
        ]

        for y_pos, label in y_levels:
            canvas.create_text(18, y_pos, text=label, fill=TEXT_LIGHT_GRAY, font=("Segoe UI", 9))
            canvas.create_line(35, y_pos, w - 10, y_pos, fill="#f1f5f9", dash=(3, 3))

        # Pipeline stages: (Stage Name, height_px, is_peak)
        bars = [
            ("PERCEIVE", 55, False),
            ("PLAN", 105, False),
            ("TYPE", 75, False),
            ("STREAM", 145, True),   # Peak Media Streaming Bar!
            ("CODE", 88, False),
            ("FILES", 110, False),
        ]

        base_y = 175
        col_width = 54
        bar_w = 26
        start_x = 55

        for i, (stage, b_h, is_peak) in enumerate(bars):
            cx = start_x + (i * col_width)
            x1 = cx - (bar_w // 2)
            x2 = cx + (bar_w // 2)
            y1 = base_y - b_h
            y2 = base_y

            color = ACCENT_GREEN if is_peak else ACCENT_MINT_BAR

            # Draw rounded pill bar
            r = bar_w // 2
            canvas.create_oval(x1, y1, x2, y1 + (r * 2), fill=color, outline="")
            canvas.create_rectangle(x1, y1 + r, x2, y2, fill=color, outline="")

            # Stage label
            canvas.create_text(cx, base_y + 16, text=stage, fill=TEXT_LIGHT_GRAY, font=("Segoe UI", 8, "bold"))

            # Floating +17.8% pin on Stream peak bar
            if is_peak:
                pin_y = y1 - 12
                canvas.create_oval(cx - 18, pin_y - 9, cx + 18, pin_y + 9, fill=ACCENT_GREEN, outline="")
                canvas.create_text(cx, pin_y, text="+17.8%", fill="#ffffff", font=("Segoe UI", 8, "bold"))
                canvas.create_oval(cx - 3, y1 - 2, cx + 3, y1 + 4, fill="#ffffff", outline=ACCENT_GREEN, width=2)

    def _draw_wave_chart(self, canvas: tk.Canvas) -> None:
        """Draw the smooth green wave line chart with soft fill."""
        w, h = 220, 45
        canvas.delete("all")

        points = [
            (5, 30),
            (35, 32),
            (65, 18),
            (95, 24),
            (125, 12),
            (155, 20),
            (185, 35),
            (215, 18),
        ]

        canvas.create_line(5, 25, 215, 25, fill="#f1f5f9", dash=(2, 2))

        flat_coords = []
        for x, y in points:
            flat_coords.extend([x, y])

        canvas.create_line(flat_coords, smooth=True, fill=ACCENT_GREEN, width=2)

    # -------------------------------------------------------------------------
    # 4. Task Runner View
    # -------------------------------------------------------------------------
    def _build_runner_view(self) -> ctk.CTkFrame:
        """Build the Prompt Runner view with emerald card styling."""
        frame = ctk.CTkScrollableFrame(self.view_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkLabel(frame, text="Autonomous Task Runner", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), text_color=TEXT_DARK, anchor="w")
        hdr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc = ctk.CTkLabel(frame, text="Instruct AutoMate to carry out complex desktop workflows with human typing, scrolling, and vision.", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY, anchor="w")
        desc.grid(row=1, column=0, sticky="w", pady=(0, 14))

        # Prompt Input Card
        prompt_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        prompt_card.grid(row=2, column=0, sticky="ew", pady=6)
        prompt_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(prompt_card, text="Task Instruction / Prompt:", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_DARK).grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        self.prompt_input = ctk.CTkTextbox(
            prompt_card,
            height=85,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            corner_radius=12,
            fg_color="#f8fafc",
            border_width=1,
            border_color="#cbd5e1",
            text_color=TEXT_DARK,
        )
        self.prompt_input.grid(row=1, column=0, padx=18, pady=4, sticky="ew")
        self.prompt_input.insert("1.0", "Open Chrome, search for the weather in Nairobi, then open YouTube and stream relaxing music.")

        # Preset Chips
        chips_frame = ctk.CTkFrame(prompt_card, fg_color="transparent")
        chips_frame.grid(row=2, column=0, padx=18, pady=(8, 16), sticky="ew")

        ctk.CTkLabel(chips_frame, text="Presets:", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_LIGHT_GRAY).pack(side="left", padx=(0, 8))

        presets = [
            ("Weather & YouTube", "Open Chrome and search for weather in Nairobi, then search YouTube for ambient music"),
            ("VS Code Coding", "Open Visual Studio Code, create a Python file with a math utility function, and run it"),
            ("File Explorer", "Open File Explorer on Desktop, create a workspace directory, and write a text note"),
            ("Tech News", "Open Chrome, navigate to news.ycombinator.com, scroll down smoothly, and read articles"),
        ]

        for title, pr_text in presets:
            chip_btn = ctk.CTkButton(
                chips_frame,
                text=f"+ {title}",
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#f1f5f9",
                hover_color="#e2e8f0",
                text_color=TEXT_DARK,
                corner_radius=12,
                command=lambda t=pr_text: self._set_prompt(t),
            )
            chip_btn.pack(side="left", padx=4)

        # Options Card
        options_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        options_card.grid(row=3, column=0, sticky="ew", pady=10)
        options_card.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(options_card, text="Execution Options & Parameters", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_DARK).grid(row=0, column=0, columnspan=4, padx=18, pady=(14, 8), sticky="w")

        # Repetition
        rep_box = ctk.CTkFrame(options_card, fg_color="transparent")
        rep_box.grid(row=1, column=0, padx=18, pady=6, sticky="w")
        ctk.CTkLabel(rep_box, text="Cycles:", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(anchor="w")
        self.rep_var = ctk.IntVar(value=1)
        self.rep_menu = ctk.CTkOptionMenu(rep_box, values=["1", "2", "3", "5", "10"], variable=self.rep_var, width=85, height=28)
        self.rep_menu.pack(anchor="w", pady=2)

        # Duration
        dur_box = ctk.CTkFrame(options_card, fg_color="transparent")
        dur_box.grid(row=1, column=1, padx=18, pady=6, sticky="w")
        ctk.CTkLabel(dur_box, text="Duration (Mins):", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(anchor="w")
        self.dur_entry = ctk.CTkEntry(dur_box, width=95, height=28)
        self.dur_entry.insert(0, "0")
        self.dur_entry.pack(anchor="w", pady=2)

        # Stream Mins
        yt_box = ctk.CTkFrame(options_card, fg_color="transparent")
        yt_box.grid(row=1, column=2, padx=18, pady=6, sticky="w")
        ctk.CTkLabel(yt_box, text="YouTube Watch:", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(anchor="w")
        self.yt_watch_entry = ctk.CTkEntry(yt_box, width=85, height=28)
        self.yt_watch_entry.insert(0, "2.5")
        self.yt_watch_entry.pack(anchor="w", pady=2)

        # Steps
        st_box = ctk.CTkFrame(options_card, fg_color="transparent")
        st_box.grid(row=1, column=3, padx=18, pady=6, sticky="w")
        ctk.CTkLabel(st_box, text="Max Steps:", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY).pack(anchor="w")
        self.steps_entry = ctk.CTkEntry(st_box, width=80, height=28)
        self.steps_entry.insert(0, str(getattr(self.cfg, "max_steps", 50)))
        self.steps_entry.pack(anchor="w", pady=2)

        # Toggles
        t_row = ctk.CTkFrame(options_card, fg_color="transparent")
        t_row.grid(row=2, column=0, columnspan=4, padx=18, pady=(8, 14), sticky="ew")

        self.fast_mode_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(t_row, text="⚡ Fast Mode", variable=self.fast_mode_var, font=ctk.CTkFont(size=11), text_color=TEXT_DARK).pack(side="left", padx=(0, 16))

        self.keep_awake_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(t_row, text="🛡 Prevent Windows Sleep", variable=self.keep_awake_var, font=ctk.CTkFont(size=11), text_color=TEXT_DARK).pack(side="left", padx=16)

        self.safety_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(t_row, text="🛑 Failsafe Safety Mode", variable=self.safety_var, font=ctk.CTkFont(size=11), text_color=TEXT_DARK).pack(side="left", padx=16)

        # Start Button
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", pady=8)

        self.start_agent_btn = ctk.CTkButton(
            btn_row,
            text="▶  START AUTONOMOUS AGENT",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            text_color="#ffffff",
            height=44,
            corner_radius=14,
            command=self.start_agent_task,
        )
        self.start_agent_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(frame, mode="indeterminate", height=6, progress_color=ACCENT_GREEN)
        self.progress_bar.grid(row=5, column=0, sticky="ew", pady=(8, 4))
        self.progress_bar.set(0)

        self.live_msg_label = ctk.CTkLabel(frame, text="Ready to begin automation.", font=ctk.CTkFont(size=11), text_color=TEXT_GRAY)
        self.live_msg_label.grid(row=6, column=0, sticky="w", pady=(0, 16))

        return frame

    def _set_prompt(self, text: str) -> None:
        self.prompt_input.delete("1.0", "end")
        self.prompt_input.insert("1.0", text)

    # -------------------------------------------------------------------------
    # 5. Workflows & Predefined Recipes View
    # -------------------------------------------------------------------------
    def _build_recipes_view(self) -> ctk.CTkFrame:
        """Build the Workflows & Recipes card catalog."""
        frame = ctk.CTkScrollableFrame(self.view_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkLabel(frame, text="Predefined Automation Workflows", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), text_color=TEXT_DARK, anchor="w")
        hdr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc = ctk.CTkLabel(frame, text="Rich multi-step human worker routines with organic typing, scrolling, and streaming pauses.", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY, anchor="w")
        desc.grid(row=1, column=0, sticky="w", pady=(0, 14))

        recipe_data = [
            (
                "browse-weather-youtube",
                "🌐 Web Browsing & YouTube Streaming",
                "Web Browsing & Media",
                "Searches weather in Nairobi on Google Chrome, queries Cloudflare AI for a dynamic YouTube topic, streams the video for 2-3 mins, skips, toggles playback, scrolls with natural reading cadence, and gracefully closes tabs.",
            ),
            (
                "code-python-project",
                "💻 VS Code Python Project",
                "Coding & VS Code",
                "Visually launches Visual Studio Code, creates a new file, types Python code character-by-character with natural keystroke variance, saves as automate_script.py, executes in terminal, and gracefully closes.",
            ),
            (
                "file-manager-organize",
                "📁 File Explorer Organizer",
                "File Management",
                "Visually opens Windows File Explorer on Desktop, creates folders and subdirectories using native Windows shortcuts, writes a manifest file, and gracefully closes Explorer.",
            ),
            (
                "full-human-worker",
                "🤖 Master Full Human Worker Routine",
                "Full Automation",
                "The comprehensive multi-stage routine chaining Web Browsing + YouTube Streaming + File Organization + VS Code Python Development with realistic contemplation transitions.",
            ),
        ]

        for idx, (rec_id, title, cat, summary) in enumerate(recipe_data, start=2):
            card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
            card.grid(row=idx, column=0, sticky="ew", pady=8)
            card.grid_columnconfigure(0, weight=1)

            t_bar = ctk.CTkFrame(card, fg_color="transparent")
            t_bar.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="ew")

            ctk.CTkLabel(t_bar, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_DARK).pack(side="left")
            b_lbl = ctk.CTkLabel(t_bar, text=cat.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=ACCENT_MINT_TEXT, fg_color=ACCENT_MINT_PILL, corner_radius=8, padx=8, pady=2)
            b_lbl.pack(side="left", padx=12)

            ctk.CTkLabel(card, text=summary, font=ctk.CTkFont(size=12), text_color=TEXT_GRAY, wraplength=780, justify="left").grid(row=1, column=0, padx=18, pady=(0, 12), sticky="w")

            act_row = ctk.CTkFrame(card, fg_color="transparent")
            act_row.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="ew")

            exec_btn = ctk.CTkButton(
                act_row,
                text="▶  Execute Workflow",
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=ACCENT_GREEN,
                hover_color=ACCENT_GREEN_HOVER,
                corner_radius=12,
                height=32,
                command=lambda r_name=rec_id: self.start_recipe_task(r_name),
            )
            exec_btn.pack(side="left", padx=(0, 12))

            ctk.CTkLabel(act_row, text="Includes organic contemplation pauses and live progress countdowns", font=ctk.CTkFont(size=11), text_color=TEXT_LIGHT_GRAY).pack(side="left")

        return frame

    # -------------------------------------------------------------------------
    # 6. Live Action Console View
    # -------------------------------------------------------------------------
    def _build_console_view(self) -> ctk.CTkFrame:
        """Build the Live Action Console view."""
        frame = ctk.CTkFrame(self.view_container, fg_color="transparent")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        top_ctrl = ctk.CTkFrame(frame, fg_color="transparent")
        top_ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(top_ctrl, text="Live Action & Contemplation Console", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_DARK).pack(side="left")

        clear_btn = ctk.CTkButton(top_ctrl, text="Clear", width=70, height=28, font=ctk.CTkFont(size=11), fg_color=CARD_BG, hover_color="#f1f5f9", text_color=TEXT_DARK, border_width=1, border_color=CARD_BORDER, corner_radius=10, command=self.clear_console)
        clear_btn.pack(side="right", padx=4)

        save_btn = ctk.CTkButton(top_ctrl, text="Export Log", width=90, height=28, font=ctk.CTkFont(size=11), fg_color=CARD_BG, hover_color="#f1f5f9", text_color=TEXT_DARK, border_width=1, border_color=CARD_BORDER, corner_radius=10, command=self.save_console_log)
        save_btn.pack(side="right", padx=4)

        # Console Textbox in sleek card
        c_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        c_card.grid(row=1, column=0, sticky="nsew")
        c_card.grid_rowconfigure(0, weight=1)
        c_card.grid_columnconfigure(0, weight=1)

        self.console_text = ctk.CTkTextbox(
            c_card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0f172a",
            text_color="#cbd5e1",
            corner_radius=14,
        )
        self.console_text.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")
        self.console_text.insert("end", "AutoMate Desktop Console initialized.\nReady to execute autonomous instructions, web browsing, coding, and file management.\n" + ("-" * 80) + "\n")

        return frame

    def clear_console(self) -> None:
        self.console_text.delete("1.0", "end")

    def save_console_log(self) -> None:
        content = self.console_text.get("1.0", "end")
        export_path = Path("automate_console_export.log")
        try:
            export_path.write_text(content, encoding="utf-8")
            self.live_msg_label.configure(text=f"Log exported successfully to {export_path.resolve()}")
        except Exception as e:
            self.live_msg_label.configure(text=f"Failed to export log: {e}")

    # -------------------------------------------------------------------------
    # 7. Settings & AI Providers View
    # -------------------------------------------------------------------------
    def _build_settings_view(self) -> ctk.CTkFrame:
        """Build the Settings and AI Provider configuration manager."""
        frame = ctk.CTkScrollableFrame(self.view_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkLabel(frame, text="Settings & AI Vision Providers", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), text_color=TEXT_DARK, anchor="w")
        hdr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc = ctk.CTkLabel(frame, text="Configure your AI reasoning backend (Cloudflare Workers AI or Anthropic Claude) and save to .env.", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY, anchor="w")
        desc.grid(row=1, column=0, sticky="w", pady=(0, 14))

        # Provider Selector Card
        prov_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        prov_card.grid(row=2, column=0, sticky="ew", pady=6)

        ctk.CTkLabel(prov_card, text="Active Vision Reasoning Provider:", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_DARK).pack(anchor="w", padx=18, pady=(14, 6))

        self.provider_var = ctk.StringVar(value=getattr(self.cfg, "provider", "cloudflare"))
        prov_segmented = ctk.CTkSegmentedButton(
            prov_card,
            values=["cloudflare", "anthropic"],
            variable=self.provider_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            selected_color=ACCENT_GREEN,
            height=32,
        )
        prov_segmented.pack(anchor="w", padx=18, pady=(0, 14))

        # Cloudflare Credentials Card
        cf_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        cf_card.grid(row=3, column=0, sticky="ew", pady=8)
        cf_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cf_card, text="Cloudflare Workers AI Credentials", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT_GREEN).grid(row=0, column=0, columnspan=2, padx=18, pady=(14, 8), sticky="w")

        ctk.CTkLabel(cf_card, text="Account ID:", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=1, column=0, padx=18, pady=6, sticky="w")
        self.cf_account_entry = ctk.CTkEntry(cf_card, height=32)
        self.cf_account_entry.insert(0, getattr(self.cfg, "cloudflare_account_id", ""))
        self.cf_account_entry.grid(row=1, column=1, padx=18, pady=6, sticky="ew")

        ctk.CTkLabel(cf_card, text="API Token:", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=2, column=0, padx=18, pady=6, sticky="w")
        self.cf_token_entry = ctk.CTkEntry(cf_card, show="*", height=32)
        self.cf_token_entry.insert(0, getattr(self.cfg, "cloudflare_api_token", ""))
        self.cf_token_entry.grid(row=2, column=1, padx=18, pady=6, sticky="ew")

        ctk.CTkLabel(cf_card, text="Vision Model:", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=3, column=0, padx=18, pady=6, sticky="w")
        self.cf_model_menu = ctk.CTkComboBox(cf_card, values=["@cf/meta/llama-3.2-11b-vision-instruct", "@cf/meta/llama-3.1-8b-instruct"], height=32)
        self.cf_model_menu.set(getattr(self.cfg, "cloudflare_model", "@cf/meta/llama-3.2-11b-vision-instruct"))
        self.cf_model_menu.grid(row=3, column=1, padx=18, pady=(6, 14), sticky="ew")

        # Anthropic Claude Card
        ant_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
        ant_card.grid(row=4, column=0, sticky="ew", pady=8)
        ant_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ant_card, text="Anthropic Claude API Credentials", font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_DARK).grid(row=0, column=0, columnspan=2, padx=18, pady=(14, 8), sticky="w")

        ctk.CTkLabel(ant_card, text="API Key:", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=1, column=0, padx=18, pady=6, sticky="w")
        self.ant_key_entry = ctk.CTkEntry(ant_card, show="*", height=32)
        self.ant_key_entry.insert(0, getattr(self.cfg, "anthropic_api_key", ""))
        self.ant_key_entry.grid(row=1, column=1, padx=18, pady=6, sticky="ew")

        ctk.CTkLabel(ant_card, text="Model Identifier:", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY).grid(row=2, column=0, padx=18, pady=6, sticky="w")
        self.ant_model_menu = ctk.CTkComboBox(ant_card, values=["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-20241022"], height=32)
        self.ant_model_menu.set(getattr(self.cfg, "model", "claude-sonnet-4-20250514"))
        self.ant_model_menu.grid(row=2, column=1, padx=18, pady=(6, 14), sticky="ew")

        # Save & Test Buttons
        save_btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        save_btn_frame.grid(row=5, column=0, sticky="ew", pady=(14, 25))

        save_cfg_btn = ctk.CTkButton(
            save_btn_frame,
            text="💾  Save Configuration to .env",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color=ACCENT_GREEN_HOVER,
            corner_radius=12,
            height=40,
            command=self.save_settings,
        )
        save_cfg_btn.pack(side="left", padx=(0, 10))

        test_conn_btn = ctk.CTkButton(
            save_btn_frame,
            text="⚡  Test Cloudflare Connection",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=CARD_BG,
            hover_color="#f1f5f9",
            text_color=TEXT_DARK,
            border_width=1,
            border_color=CARD_BORDER,
            corner_radius=12,
            height=40,
            command=self.test_ai_connection,
        )
        test_conn_btn.pack(side="left")

        return frame

    def save_settings(self) -> None:
        env_path = Path(".env")
        lines = [
            "# AutoMate Environment Configuration",
            f"PROVIDER={self.provider_var.get()}",
            f"CLOUDFLARE_ACCOUNT_ID={self.cf_account_entry.get().strip()}",
            f"CLOUDFLARE_API_TOKEN={self.cf_token_entry.get().strip()}",
            f"CLOUDFLARE_MODEL={self.cf_model_menu.get().strip()}",
            f"ANTHROPIC_API_KEY={self.ant_key_entry.get().strip()}",
            f"MODEL={self.ant_model_menu.get().strip()}",
            f"MAX_STEPS={self.steps_entry.get().strip() or '50'}",
            f"SAFETY_MODE={str(self.safety_var.get()).lower()}",
            f"KEEP_AWAKE={str(self.keep_awake_var.get()).lower()}",
        ]
        try:
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.live_msg_label.configure(text="Settings saved successfully to .env")
            try:
                self.cfg = get_config()
            except Exception:
                pass
        except Exception as e:
            self.live_msg_label.configure(text=f"Failed to write .env: {e}")

    def test_ai_connection(self) -> None:
        self.live_msg_label.configure(text="Testing connection to Cloudflare Workers AI...")
        acct = self.cf_account_entry.get().strip()
        tok = self.cf_token_entry.get().strip()

        def _do_test() -> None:
            try:
                import requests
                headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
                url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/meta/llama-3.1-8b-instruct"
                payload = {"messages": [{"role": "user", "content": "Respond with 'OK' if you can read this."}]}
                r = requests.post(url, headers=headers, json=payload, timeout=10.0)
                if r.status_code == 200:
                    self.log_queue.put(("OUTPUT", "INFO", "Cloudflare Workers AI test: SUCCESS (HTTP 200)"))
                    self.after(0, lambda: self.live_msg_label.configure(text="Cloudflare AI test PASSED! Connection verified."))
                else:
                    msg = f"Cloudflare AI test: FAILED ({r.status_code})"
                    self.log_queue.put(("OUTPUT", "WARNING", msg))
                    self.after(0, lambda: self.live_msg_label.configure(text=msg))
            except Exception as ex:
                self.log_queue.put(("OUTPUT", "ERROR", f"Cloudflare test error: {ex}"))
                self.after(0, lambda: self.live_msg_label.configure(text=f"Connection error: {ex}"))

        threading.Thread(target=_do_test, daemon=True).start()

    # -------------------------------------------------------------------------
    # 8. Tools Catalog View
    # -------------------------------------------------------------------------
    def _build_tools_view(self) -> ctk.CTkFrame:
        """Build the Tools Catalog view."""
        frame = ctk.CTkScrollableFrame(self.view_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkLabel(frame, text="Desktop Automation Tools Catalog", font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"), text_color=TEXT_DARK, anchor="w")
        hdr.grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc = ctk.CTkLabel(frame, text="Every built-in tool accessible to the vision agent and automation workflows.", font=ctk.CTkFont(size=12), text_color=TEXT_GRAY, anchor="w")
        desc.grid(row=1, column=0, sticky="w", pady=(0, 14))

        tool_cards = [
            ("click_at", "Mouse", "Click at specific screen coordinates (x, y) with specified mouse button and double-click option."),
            ("move_mouse", "Mouse", "Move cursor smoothly to target coordinates with natural human-grade bezier path."),
            ("reading_scroll", "Mouse / Human", "Progressive multi-stage scrolling simulating natural human reading cadence."),
            ("human_type", "Keyboard / Human", "Visible character-by-character typing with natural keystroke timing variance."),
            ("press_key", "Keyboard", "Press an individual keyboard key (e.g. 'enter', 'f5', 'esc', 'k', 'space')."),
            ("hotkey", "Keyboard", "Trigger keyboard combination (e.g. 'ctrl+c', 'win+r', 'alt+f4', 'ctrl+shift+n')."),
            ("open_app", "Applications", "Launch Windows applications (Chrome, VS Code, Notepad, File Explorer, etc.)."),
            ("close_app", "Applications", "Gracefully close application windows by name."),
            ("open_url", "Web Browsing", "Navigate browser directly to destination URL with tab control."),
            ("search_youtube", "YouTube", "Search YouTube directly in Google Chrome."),
            ("play_youtube_video", "YouTube", "Click and play the first video on YouTube search results page."),
            ("toggle_youtube_playback", "YouTube", "Toggle video playback (play / pause) on YouTube via 'k' hotkey."),
            ("next_youtube_video", "YouTube", "Skip to next video in YouTube queue (Shift+N)."),
            ("visual_create_folder", "File Management", "Visually create a new folder inside active File Explorer using native Windows shortcuts."),
            ("visual_code_editor", "Coding / VS Code", "Visually type code into VS Code, save it, name it, and execute in terminal."),
            ("open_file_explorer", "File Management", "Open Windows File Explorer at specified directory."),
            ("run_powershell", "System / Shell", "Execute PowerShell or command line instruction and capture output."),
            ("screenshot", "Vision", "Capture full-screen high-resolution desktop screenshot for perception analysis."),
            ("sleep", "Timing", "Pause execution for specified duration to allow UI animations or content loading."),
        ]

        for i, (name, cat, doc) in enumerate(tool_cards, start=2):
            card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=CARD_BORDER)
            card.grid(row=i, column=0, sticky="ew", pady=5)
            card.grid_columnconfigure(0, weight=1)

            t_bar = ctk.CTkFrame(card, fg_color="transparent")
            t_bar.grid(row=0, column=0, padx=18, pady=(10, 2), sticky="ew")

            ctk.CTkLabel(t_bar, text=name, font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=ACCENT_GREEN).pack(side="left")
            b_lbl = ctk.CTkLabel(t_bar, text=cat.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=ACCENT_MINT_TEXT, fg_color=ACCENT_MINT_PILL, corner_radius=6, padx=6, pady=1)
            b_lbl.pack(side="left", padx=10)

            ctk.CTkLabel(card, text=doc, font=ctk.CTkFont(size=11), text_color=TEXT_GRAY, justify="left").grid(row=1, column=0, padx=18, pady=(0, 10), sticky="w")

        return frame

    # -------------------------------------------------------------------------
    # Execution & Background Threading
    # -------------------------------------------------------------------------
    def start_agent_task(self) -> None:
        if self.is_running:
            return

        instruction = self.prompt_input.get("1.0", "end").strip()
        if not instruction:
            self.live_msg_label.configure(text="Please enter an instruction prompt before starting.")
            return

        repeat = int(self.rep_var.get())
        try:
            duration_mins = float(self.dur_entry.get().strip() or "0")
        except ValueError:
            duration_mins = 0.0

        try:
            watch_mins = float(self.yt_watch_entry.get().strip() or "2.5")
            os.environ["AUTOMATE_WATCH_MINS"] = str(watch_mins)
        except ValueError:
            pass

        if self.fast_mode_var.get():
            os.environ["AUTOMATE_FAST_MODE"] = "1"
        else:
            os.environ.pop("AUTOMATE_FAST_MODE", None)

        self._set_running_state(True, "Running Autonomous Agent...")
        reset_recipe_stop()

        def _worker() -> None:
            try:
                from automate.agent import AutoMateAgent
                from automate.cli import get_effective_config

                cfg = get_effective_config(
                    provider=self.provider_var.get(),
                    cf_account_id=self.cf_account_entry.get().strip() or None,
                    cf_token=self.cf_token_entry.get().strip() or None,
                    cf_model=self.cf_model_menu.get().strip() or None,
                    model=self.ant_model_menu.get().strip() or None,
                    api_key=self.ant_key_entry.get().strip() or None,
                    max_steps=int(self.steps_entry.get().strip() or "50"),
                    keep_awake=self.keep_awake_var.get(),
                    safety_mode=self.safety_var.get(),
                )

                self.active_agent = AutoMateAgent(config=cfg)

                total_sec = duration_mins * 60.0
                end_time = (time.time() + total_sec) if total_sec > 0 else None
                cycle = 1

                while True:
                    if end_time and time.time() >= end_time:
                        self.log_queue.put(("OUTPUT", "INFO", f"Duration limit reached ({duration_mins}m)."))
                        break
                    if repeat > 1 and cycle > repeat:
                        self.log_queue.put(("OUTPUT", "INFO", f"All {repeat} repetition cycles completed."))
                        break

                    self.log_queue.put(("OUTPUT", "INFO", f"--- Starting Agent Cycle {cycle} ---"))
                    res = self.active_agent.run(instruction)

                    if res.success:
                        self.log_queue.put(("OUTPUT", "INFO", f"Cycle {cycle} finished successfully: {res.final_message}"))
                    else:
                        self.log_queue.put(("OUTPUT", "WARNING", f"Cycle {cycle} halted: {res.error or res.final_message}"))

                    cycle += 1
                    if (repeat > 1 and cycle <= repeat) or (end_time and time.time() < end_time):
                        time.sleep(2.0)

            except InterruptedError:
                self.log_queue.put(("OUTPUT", "WARNING", "Agent execution stopped by user."))
            except Exception as e:
                self.log_queue.put(("OUTPUT", "ERROR", f"Agent execution error: {e}"))
            finally:
                self.after(0, lambda: self._set_running_state(False, "Agent run finished."))

        self.current_thread = threading.Thread(target=_worker, daemon=True)
        self.current_thread.start()

    def start_recipe_task(self, recipe_name: str) -> None:
        if self.is_running:
            return

        recipe = get_recipe(recipe_name)
        if not recipe:
            return

        repeat = int(self.rep_var.get())
        try:
            duration_mins = float(self.dur_entry.get().strip() or "0")
        except ValueError:
            duration_mins = 0.0

        try:
            watch_mins = float(self.yt_watch_entry.get().strip() or "2.5")
            os.environ["AUTOMATE_WATCH_MINS"] = str(watch_mins)
        except ValueError:
            pass

        if self.fast_mode_var.get():
            os.environ["AUTOMATE_FAST_MODE"] = "1"
        else:
            os.environ.pop("AUTOMATE_FAST_MODE", None)

        self._set_running_state(True, f"Executing Recipe: {recipe.name}...")
        reset_recipe_stop()
        self.switch_view("console")

        def _worker() -> None:
            try:
                tools = DesktopToolSuite()
                total_sec = duration_mins * 60.0
                end_time = (time.time() + total_sec) if total_sec > 0 else None
                cycle = 1

                while True:
                    if is_recipe_stopped():
                        break
                    if end_time and time.time() >= end_time:
                        self.log_queue.put(("OUTPUT", "INFO", f"Duration limit reached ({duration_mins}m)."))
                        break
                    if repeat > 1 and cycle > repeat:
                        self.log_queue.put(("OUTPUT", "INFO", f"Completed {repeat} recipe cycles."))
                        break

                    self.log_queue.put(("OUTPUT", "INFO", f"--- Recipe Cycle {cycle}: {recipe.name} ---"))
                    res = recipe.execute(tools)
                    self.log_queue.put(("OUTPUT", "INFO", f"Cycle {cycle} complete: {res}"))

                    cycle += 1
                    if (repeat > 1 and cycle <= repeat) or (end_time and time.time() < end_time):
                        time.sleep(2.0)

            except InterruptedError:
                self.log_queue.put(("OUTPUT", "WARNING", "Recipe execution stopped by user."))
            except Exception as e:
                self.log_queue.put(("OUTPUT", "ERROR", f"Recipe execution error: {e}"))
            finally:
                self.after(0, lambda: self._set_running_state(False, "Recipe run finished."))

        self.current_thread = threading.Thread(target=_worker, daemon=True)
        self.current_thread.start()

    def emergency_stop(self) -> None:
        if not self.is_running:
            self.live_msg_label.configure(text="No active execution to stop.")
            return

        self.live_msg_label.configure(text="Halting execution (Emergency Stop requested)...")
        stop_recipe()
        if self.active_agent:
            try:
                self.active_agent.stop()
            except Exception:
                pass

        self.log_queue.put(("OUTPUT", "WARNING", "EMERGENCY STOP TRIGGERED BY USER"))

    def _set_running_state(self, running: bool, status_msg: str) -> None:
        self.is_running = running
        if running:
            self.start_time = time.time()
            self.progress_bar.start()
            self.start_agent_btn.configure(state="disabled")
        else:
            self.progress_bar.stop()
            self.progress_bar.set(0)
            self.start_agent_btn.configure(state="normal")
            self.active_agent = None

        self.live_msg_label.configure(text=status_msg)

    def _process_log_queue(self) -> None:
        try:
            count = 0
            while count < 30:
                item = self.log_queue.get_nowait()
                _, level, msg = item
                clean = msg.strip()
                if clean:
                    self.console_text.insert("end", f"{clean}\n")
                    self.console_text.see("end")
                count += 1
        except queue.Empty:
            pass

        self.after(100, self._process_log_queue)


def launch_ui() -> None:
    app = AutoMateApp()
    app.mainloop()


if __name__ == "__main__":
    launch_ui()
