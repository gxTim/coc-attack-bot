"""
GUI - CustomTkinter-based graphical user interface for the COC Attack Bot
"""

import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from ..bot_controller import BotController

# Apply global appearance settings
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------------------
# Dark theme color palette
# ---------------------------------------------------------------------------

BG_MAIN  = "#1a1a2e"   # root / sidebar background
BG_SECT  = "#16213e"   # section card frames
BG_HOVER = "#0f3460"   # hover / active state
ACCENT   = "#00b894"   # green accent (active / on states)
ACCENT_H = "#007a61"   # darker green for pressed/hover
BORDER   = "#0f3460"   # section frame border colour
TEXT     = "#e0e0e0"   # primary text
TEXT_DIM = "#888888"   # secondary / label text
BTN_FG   = "#16213e"   # default button face colour


# ---------------------------------------------------------------------------
# Helper: create a dark bordered section frame
# ---------------------------------------------------------------------------

def _make_section(parent: ctk.CTkFrame, title: str, **kw) -> ctk.CTkFrame:
    """Return a dark bordered frame with a small section-title label at the top."""
    frame = ctk.CTkFrame(
        parent,
        fg_color=BG_SECT,
        border_width=1,
        border_color=BORDER,
        corner_radius=6,
        **kw,
    )
    ctk.CTkLabel(
        frame,
        text=title.upper(),
        text_color=TEXT_DIM,
        font=("", 10),
        anchor="w",
    ).grid(row=0, column=0, columnspan=10, padx=8, pady=(4, 0), sticky="w")
    return frame


# ---------------------------------------------------------------------------
# Log handler
# ---------------------------------------------------------------------------

class GUILogHandler:
    """Routes log messages to the GUI log panel in a thread-safe manner."""

    LEVEL_COLOURS = {
        "INFO": TEXT,
        "WARNING": "#FFA500",
        "ERROR": "#FF4444",
        "CRITICAL": "#FF0000",
        "SUCCESS": ACCENT,
        "LOOT": "#44DDFF",
    }

    def __init__(self, log_textbox: ctk.CTkTextbox, root: ctk.CTk):
        self.log_textbox = log_textbox
        self.root = root

    def write(self, message: str, level: str = "INFO") -> None:
        """Thread-safe log writing to the GUI panel with level-based coloring."""
        colour = self.LEVEL_COLOURS.get(level.upper(), self.LEVEL_COLOURS["INFO"])
        tag = f"level_{level.upper()}"

        def _append():
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                text_widget = self.log_textbox._textbox
                # Configure the colour tag on first use
                if tag not in text_widget.tag_names():
                    text_widget.tag_configure(tag, foreground=colour)
                self.log_textbox.configure(state="normal")
                text_widget.insert("end", f"[{ts}] [{level}] {message}\n", tag)
                self.log_textbox.configure(state="disabled")
                self.log_textbox.see("end")
            except Exception:
                pass

        try:
            self.root.after(0, _append)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------

class DashboardPage(ctk.CTkFrame):
    """Live statistics dashboard for the auto-attack system."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._polling = False
        self._ever_started = False
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        # Status section
        status_sec = _make_section(self, "Status")
        status_sec.grid(row=0, column=0, padx=16, pady=(14, 6), sticky="ew")
        status_sec.columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_sec, text="IDLE", font=("", 26, "bold"), text_color=TEXT_DIM
        )
        self.status_label.grid(row=1, column=0, pady=(4, 10))

        # Loot section
        loot_sec = _make_section(self, "Loot Collected")
        loot_sec.grid(row=1, column=0, padx=16, pady=6, sticky="ew")
        loot_sec.columnconfigure((0, 1, 2), weight=1)

        self.gold_label = ctk.CTkLabel(loot_sec, text="💰 Gold\n—", font=("", 13), text_color=TEXT)
        self.gold_label.grid(row=1, column=0, padx=12, pady=(4, 12))

        self.elixir_label = ctk.CTkLabel(loot_sec, text="💧 Elixir\n—", font=("", 13), text_color=TEXT)
        self.elixir_label.grid(row=1, column=1, padx=12, pady=(4, 12))

        self.dark_label = ctk.CTkLabel(loot_sec, text="⚫ Dark\n—", font=("", 13), text_color=TEXT)
        self.dark_label.grid(row=1, column=2, padx=12, pady=(4, 12))

        # Stats section
        stats_sec = _make_section(self, "Attack Stats")
        stats_sec.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        stats_sec.columnconfigure((0, 1), weight=1)

        self.attacks_label = ctk.CTkLabel(stats_sec, text="Attacks: 0  |  Success: 0%", font=("", 12), text_color=TEXT)
        self.attacks_label.grid(row=1, column=0, columnspan=2, padx=8, pady=(4, 2))

        self.rate_label = ctk.CTkLabel(stats_sec, text="Attacks/hour: 0", font=("", 12), text_color=TEXT)
        self.rate_label.grid(row=2, column=0, padx=8, pady=2, sticky="w")

        self.runtime_label = ctk.CTkLabel(stats_sec, text="Runtime: 0h 0m", font=("", 12), text_color=TEXT)
        self.runtime_label.grid(row=2, column=1, padx=8, pady=2, sticky="e")

        self.last_attack_label = ctk.CTkLabel(stats_sec, text="Last attack: —", font=("", 12), text_color=TEXT_DIM)
        self.last_attack_label.grid(row=3, column=0, columnspan=2, padx=8, pady=(2, 10))

    def on_show(self):
        """Called when this page is raised; starts the polling loop."""
        if not self._polling:
            self._polling = True
            self.update_stats()

    def update_stats(self):
        """Periodically refresh dashboard statistics."""
        try:
            if self.bot.is_auto_attacking():
                self._ever_started = True
                stats = self.bot.get_auto_attack_stats()
                self.status_label.configure(text="RUNNING", text_color=ACCENT)

                total = stats.get("total_attacks", 0)
                success_rate = stats.get("success_rate", 0.0)
                aph = stats.get("attacks_per_hour", 0.0)
                runtime_h = stats.get("runtime_hours", 0.0)
                last = stats.get("last_attack", "—")
                loot = stats.get("total_loot", {})

                h = int(runtime_h)
                m = int((runtime_h - h) * 60)

                self.attacks_label.configure(
                    text=f"Attacks: {total}  |  Success: {success_rate:.1f}%"
                )
                self.rate_label.configure(text=f"Attacks/hour: {aph:.1f}")
                self.runtime_label.configure(text=f"Runtime: {h}h {m}m")
                self.last_attack_label.configure(text=f"Last attack: {last}")
                self.gold_label.configure(text=f"💰 Gold\n{loot.get('gold', 0):,}")
                self.elixir_label.configure(text=f"💧 Elixir\n{loot.get('elixir', 0):,}")
                self.dark_label.configure(text=f"⚫ Dark\n{loot.get('dark_elixir', 0):,}")
            else:
                if self._ever_started:
                    self.status_label.configure(text="STOPPED", text_color="#FF4444")
                else:
                    self.status_label.configure(text="IDLE", text_color=TEXT_DIM)
        except Exception:
            pass

        self.after(2000, self.update_stats)


# ---------------------------------------------------------------------------
# Auto Attack page
# ---------------------------------------------------------------------------

class AutoAttackPage(ctk.CTkFrame):
    """Configuration and control page for the automated attack system."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._session_vars: dict = {}
        self._build_ui()
        self._refresh_sessions()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # --- Session list ---
        sess_sec = _make_section(self, "Attack Sessions")
        sess_sec.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 4), sticky="ew")
        sess_sec.columnconfigure(0, weight=1)

        self.sessions_frame = ctk.CTkScrollableFrame(sess_sec, fg_color=BG_SECT, height=120)
        self.sessions_frame.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        ctk.CTkButton(
            sess_sec, text="↺ Refresh", command=self._refresh_sessions,
            width=100, height=28, fg_color=BTN_FG, hover_color=BG_HOVER,
            text_color=TEXT, font=("", 11),
        ).grid(row=2, column=0, pady=(2, 6))

        # --- Loot requirements ---
        loot_sec = _make_section(self, "Loot Requirements")
        loot_sec.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        loot_sec.columnconfigure((1, 3, 5), weight=1)

        for col, (lbl, attr) in enumerate([
            ("Min Gold:", "gold_entry"),
            ("Min Elixir:", "elixir_entry"),
            ("Min Dark:", "dark_entry"),
        ]):
            ctk.CTkLabel(loot_sec, text=lbl, text_color=TEXT_DIM, font=("", 11)).grid(
                row=1, column=col * 2, padx=(8, 2), pady=6, sticky="e"
            )
            entry = ctk.CTkEntry(
                loot_sec, placeholder_text="0", width=90, height=28,
                fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
            )
            entry.grid(row=1, column=col * 2 + 1, padx=(2, 8), pady=6)
            setattr(self, attr, entry)

        # --- Options row: TH level + AI ---
        opt_sec = _make_section(self, "Options")
        opt_sec.grid(row=2, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        opt_sec.columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(opt_sec, text="Max TH Level:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=6, sticky="e"
        )
        self.th_dropdown = ctk.CTkOptionMenu(
            opt_sec, values=[str(i) for i in range(1, 17)],
            width=70, height=28, fg_color=BTN_FG, button_color=BG_HOVER,
            dropdown_fg_color=BG_SECT, text_color=TEXT,
        )
        self.th_dropdown.set("16")
        self.th_dropdown.grid(row=1, column=1, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(opt_sec, text="AI Analysis:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=2, padx=8, pady=6, sticky="e"
        )
        self.ai_switch = ctk.CTkSwitch(
            opt_sec, text="", width=46, height=24,
            progress_color=ACCENT, button_color=TEXT,
        )
        self.ai_switch.grid(row=1, column=3, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(opt_sec, text="Gemini API Key:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=2, column=0, padx=8, pady=6, sticky="e"
        )
        self.api_key_entry = ctk.CTkEntry(
            opt_sec, placeholder_text="API key", show="*", width=220, height=28,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.api_key_entry.grid(row=2, column=1, columnspan=3, padx=8, pady=6, sticky="w")

        # --- Troop bar calibration ---
        ctk.CTkButton(
            self, text="🎯 Calibrate Troop Bar", command=self._calibrate_troop_bar,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, height=30,
        ).grid(row=3, column=0, columnspan=2, pady=6)

        # --- Start / Stop ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=8)

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶ Start Auto Attack",
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#000000",
            width=180, height=34, font=("", 12, "bold"),
            command=self._start_attack,
        )
        self.start_btn.grid(row=0, column=0, padx=10)

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="⏹ Stop",
            fg_color="#8B0000", hover_color="#5c0000", text_color=TEXT,
            width=100, height=34, font=("", 12, "bold"),
            command=self._stop_attack, state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, padx=10)

        self._load_config_values()

    def _load_config_values(self):
        cfg = self.bot.config
        self.gold_entry.delete(0, "end")
        self.gold_entry.insert(0, str(cfg.get("ai_analyzer.min_gold", 300000)))
        self.elixir_entry.delete(0, "end")
        self.elixir_entry.insert(0, str(cfg.get("ai_analyzer.min_elixir", 300000)))
        self.dark_entry.delete(0, "end")
        self.dark_entry.insert(0, str(cfg.get("ai_analyzer.min_dark_elixir", 2000)))
        self.th_dropdown.set(str(cfg.get("auto_attacker.max_th_level", 16)))
        if cfg.get("ai_analyzer.enabled", False):
            self.ai_switch.select()
        api = cfg.get("ai_analyzer.google_gemini_api_key", "")
        if api and api != "YOUR_GEMINI_API_KEY_HERE":
            self.api_key_entry.delete(0, "end")
            self.api_key_entry.insert(0, api)

    def _refresh_sessions(self):
        for widget in self.sessions_frame.winfo_children():
            widget.destroy()
        self._session_vars = {}
        sessions = self.bot.list_recorded_attacks()
        if not sessions:
            ctk.CTkLabel(self.sessions_frame, text="No recordings found.", text_color=TEXT_DIM).pack(padx=8, pady=4)
        for name in sessions:
            var = tk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(
                self.sessions_frame, text=name, variable=var,
                text_color=TEXT, checkmark_color="#000000",
                fg_color=ACCENT, hover_color=ACCENT_H,
            )
            cb.pack(anchor="w", padx=8, pady=2)
            self._session_vars[name] = var

    def _calibrate_troop_bar(self):
        win = ctk.CTkToplevel(self)
        win.title("Troop Bar Calibration")
        win.geometry("420x220")
        win.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(
            win,
            text=(
                "Troop Bar Calibration\n\n"
                "1. Make sure Clash of Clans is visible on screen.\n"
                "2. Press F2 to begin calibration.\n"
                "3. Click the leftmost troop slot, then the rightmost.\n"
                "4. The bot will save the calibration automatically."
            ),
            justify="left", text_color=TEXT,
        ).pack(padx=20, pady=20)
        ctk.CTkButton(win, text="Close", command=win.destroy,
                      fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT).pack(pady=8)

    def _start_attack(self):
        selected = [name for name, var in self._session_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("No Sessions", "Please select at least one attack session.")
            return
        try:
            min_gold = int(self.gold_entry.get() or 300000)
            min_elixir = int(self.elixir_entry.get() or 300000)
            min_dark = int(self.dark_entry.get() or 2000)
        except ValueError:
            messagebox.showerror("Invalid Input", "Loot requirements must be integers.")
            return

        ai_enabled = self.ai_switch.get()
        self.bot.config.set("ai_analyzer.enabled", bool(ai_enabled))
        api_key = self.api_key_entry.get().strip()
        if api_key:
            self.bot.config.set("ai_analyzer.google_gemini_api_key", api_key)
        th = int(self.th_dropdown.get())
        self.bot.config.set("auto_attacker.max_th_level", th)

        # Disable the start button BEFORE starting the thread to prevent
        # double-clicks from launching a second concurrent attack.
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        threading.Thread(
            target=self.bot.start_auto_attack,
            args=(selected, min_gold, min_elixir, min_dark),
            daemon=True,
        ).start()

    def _stop_attack(self):
        threading.Thread(target=self.bot.stop_auto_attack, daemon=True).start()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def on_show(self):
        self._refresh_sessions()
        if self.bot.is_auto_attacking():
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")


# ---------------------------------------------------------------------------
# Recording page
# ---------------------------------------------------------------------------

class RecordingPage(ctk.CTkFrame):
    """Page for managing and creating attack recordings."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._recording_start: Optional[float] = None
        self._build_ui()
        self._refresh_recordings()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        # --- Controls section ---
        ctrl_sec = _make_section(self, "New Recording")
        ctrl_sec.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        ctrl_sec.columnconfigure(1, weight=1)

        ctk.CTkLabel(ctrl_sec, text="Session name:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=6, sticky="e"
        )
        self.name_entry = ctk.CTkEntry(
            ctrl_sec, placeholder_text="e.g. goblin_barch", width=220, height=28,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.name_entry.grid(row=1, column=1, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(ctrl_sec, text="Auto-detect clicks:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=2, column=0, padx=8, pady=4, sticky="e"
        )
        self.detect_switch = ctk.CTkSwitch(
            ctrl_sec, text="", width=46, height=24,
            progress_color=ACCENT, button_color=TEXT,
        )
        self.detect_switch.select()
        self.detect_switch.grid(row=2, column=1, padx=8, pady=4, sticky="w")

        self.record_btn = ctk.CTkButton(
            ctrl_sec, text="⏺ Start Recording",
            fg_color="#8B0000", hover_color="#5c0000", text_color=TEXT,
            width=180, height=32, font=("", 12, "bold"),
            command=self._toggle_recording,
        )
        self.record_btn.grid(row=3, column=0, columnspan=2, pady=(4, 8))

        self.rec_status = ctk.CTkLabel(ctrl_sec, text="", text_color="#FFA500", font=("", 11))
        self.rec_status.grid(row=4, column=0, columnspan=2, pady=(0, 4))

        # --- Recordings list section ---
        list_sec = _make_section(self, "Saved Recordings")
        list_sec.grid(row=1, column=0, padx=12, pady=4, sticky="ew")
        list_sec.columnconfigure(0, weight=1)

        self.list_frame = ctk.CTkScrollableFrame(list_sec, fg_color=BG_SECT, height=220)
        self.list_frame.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        ctk.CTkButton(
            list_sec, text="↺ Refresh", command=self._refresh_recordings,
            width=90, height=28, fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
        ).grid(row=2, column=0, pady=(2, 6))

    def _toggle_recording(self):
        if not self.bot.is_recording:
            name = self.name_entry.get().strip()
            if not name:
                messagebox.showwarning("No Name", "Please enter a session name.")
                return
            self.bot.start_attack_recording(name)
            self._recording_start = time.time()
            self.record_btn.configure(text="⏹ Stop Recording", fg_color="#555555")
            self._update_rec_status()
        else:
            self.bot.stop_attack_recording()
            self._recording_start = None
            self.record_btn.configure(text="⏺ Start Recording", fg_color="#8B0000")
            self.rec_status.configure(text="")
            self._refresh_recordings()

    def _update_rec_status(self):
        if self.bot.is_recording and self._recording_start is not None:
            elapsed = int(time.time() - self._recording_start)
            m, s = divmod(elapsed, 60)
            self.rec_status.configure(text=f"● Recording... {m:02d}:{s:02d}")
            self.after(1000, self._update_rec_status)

    def _refresh_recordings(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        sessions = self.bot.list_recorded_attacks()
        if not sessions:
            ctk.CTkLabel(self.list_frame, text="No recordings yet.", text_color=TEXT_DIM).pack(padx=8, pady=4)
            return
        for name in sessions:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(row, text=name, width=200, anchor="w", text_color=TEXT, font=("", 11)).pack(side="left", padx=4)
            info = self.bot.attack_recorder.get_recording_info(name)
            if info:
                actions = info.get("action_count", 0)
                dur = info.get("duration", 0.0)
                ctk.CTkLabel(row, text=f"{actions} actions  {dur:.1f}s",
                              text_color=TEXT_DIM, font=("", 10)).pack(side="left", padx=8)
            ctk.CTkButton(
                row, text="🗑", width=28, height=24, fg_color="transparent",
                hover_color=BG_HOVER, text_color="#FF4444",
                command=lambda n=name: self._delete_recording(n),
            ).pack(side="right", padx=4)

    def _delete_recording(self, name: str):
        if messagebox.askyesno("Delete", f"Delete recording '{name}'?"):
            self.bot.attack_recorder.delete_recording(name)
            self._refresh_recordings()

    def on_show(self):
        self._refresh_recordings()


# ---------------------------------------------------------------------------
# Playback page
# ---------------------------------------------------------------------------

class PlaybackPage(ctk.CTkFrame):
    """Page for playing back recorded attack sessions."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._play_thread: Optional[threading.Thread] = None
        self._build_ui()
        self._refresh_sessions()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        # --- Session selector ---
        sel_sec = _make_section(self, "Session")
        sel_sec.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        sel_sec.columnconfigure(1, weight=1)

        ctk.CTkLabel(sel_sec, text="Recording:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=6, sticky="e"
        )
        self.session_menu = ctk.CTkOptionMenu(
            sel_sec, values=["(none)"], width=220, height=28,
            fg_color=BTN_FG, button_color=BG_HOVER,
            dropdown_fg_color=BG_SECT, text_color=TEXT,
        )
        self.session_menu.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        ctk.CTkButton(
            sel_sec, text="↺", width=28, height=28, command=self._refresh_sessions,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 12),
        ).grid(row=1, column=2, padx=4, pady=6)

        # --- Speed control ---
        speed_sec = _make_section(self, "Playback Speed")
        speed_sec.grid(row=1, column=0, padx=12, pady=4, sticky="ew")
        speed_sec.columnconfigure(2, weight=1)

        ctk.CTkLabel(speed_sec, text="Speed:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=6, sticky="e"
        )
        self.speed_label = ctk.CTkLabel(speed_sec, text="1.0×", width=40, text_color=TEXT, font=("", 11))
        self.speed_label.grid(row=1, column=1, padx=4, pady=6)
        self.speed_slider = ctk.CTkSlider(
            speed_sec, from_=0.1, to=5.0, number_of_steps=49,
            command=self._on_speed_change, width=200,
            progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_H,
        )
        self.speed_slider.set(1.0)
        self.speed_slider.grid(row=1, column=2, padx=8, pady=6, sticky="ew")

        # --- Progress / status ---
        prog_sec = _make_section(self, "Progress")
        prog_sec.grid(row=2, column=0, padx=12, pady=4, sticky="ew")
        prog_sec.columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(prog_sec, height=8, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, padx=12, pady=(4, 2), sticky="ew")

        self.pb_status = ctk.CTkLabel(prog_sec, text="Stopped", text_color=TEXT_DIM, font=("", 11))
        self.pb_status.grid(row=2, column=0, pady=(0, 8))

        # --- Controls ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=10)

        self.play_btn = ctk.CTkButton(
            btn_frame, text="▶ Play",
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#000000",
            width=120, height=34, font=("", 12, "bold"),
            command=self._play,
        )
        self.play_btn.grid(row=0, column=0, padx=8)

        self.stop_pb_btn = ctk.CTkButton(
            btn_frame, text="⏹ Stop",
            fg_color="#8B0000", hover_color="#5c0000", text_color=TEXT,
            width=80, height=34, font=("", 12, "bold"),
            command=self._stop_playback, state="disabled",
        )
        self.stop_pb_btn.grid(row=0, column=1, padx=8)

    def _on_speed_change(self, value):
        self.speed_label.configure(text=f"{float(value):.1f}×")

    def _refresh_sessions(self):
        sessions = self.bot.list_recorded_attacks()
        if sessions:
            self.session_menu.configure(values=sessions)
            self.session_menu.set(sessions[0])
        else:
            self.session_menu.configure(values=["(none)"])
            self.session_menu.set("(none)")

    def _play(self):
        session = self.session_menu.get()
        if not session or session == "(none)":
            messagebox.showwarning("No Session", "Please select a recording to play.")
            return
        speed = float(self.speed_slider.get())
        self.bot.config.set("bot.playback_speed", speed)
        self.pb_status.configure(text="Playing...")
        self.play_btn.configure(state="disabled")
        self.stop_pb_btn.configure(state="normal")
        self.progress.set(0)

        def run():
            self.bot.play_attack(session)
            self.after(0, self._on_play_done)

        self._play_thread = threading.Thread(target=run, daemon=True)
        self._play_thread.start()

    def _stop_playback(self):
        self.bot.is_playing = False
        self._on_play_done()

    def _on_play_done(self):
        self.pb_status.configure(text="Stopped")
        self.play_btn.configure(state="normal")
        self.stop_pb_btn.configure(state="disabled")
        self.progress.set(0)

    def on_show(self):
        self._refresh_sessions()


# ---------------------------------------------------------------------------
# Coordinates page
# ---------------------------------------------------------------------------

class CoordinatesPage(ctk.CTkFrame):
    """Page for managing mapped button coordinates."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._build_ui()
        self._refresh_coords()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        # --- Action buttons ---
        act_sec = _make_section(self, "Actions")
        act_sec.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        act_sec.columnconfigure((0, 1, 2, 3), weight=1)

        for col, (text, cmd) in enumerate([
            ("▶ Start Mapping", self._start_mapping),
            ("🎯 Calibrate", self._calibrate),
            ("📤 Export", self._export),
            ("📥 Import", self._import),
        ]):
            ctk.CTkButton(
                act_sec, text=text, command=cmd,
                height=30, fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
            ).grid(row=1, column=col, padx=6, pady=(4, 8))

        # --- Coordinates list ---
        list_sec = _make_section(self, "Mapped Coordinates")
        list_sec.grid(row=1, column=0, padx=12, pady=4, sticky="ew")
        list_sec.columnconfigure(0, weight=1)

        self.coords_frame = ctk.CTkScrollableFrame(list_sec, fg_color=BG_SECT, height=300)
        self.coords_frame.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        ctk.CTkButton(
            list_sec, text="↺ Refresh", command=self._refresh_coords,
            width=90, height=28, fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
        ).grid(row=2, column=0, pady=(2, 6))

    def _refresh_coords(self):
        for widget in self.coords_frame.winfo_children():
            widget.destroy()
        coords = self.bot.get_mapped_coordinates()
        if not coords:
            ctk.CTkLabel(self.coords_frame, text="No coordinates mapped yet.", text_color=TEXT_DIM).pack(padx=8, pady=4)
            return
        # Header row
        header = ctk.CTkFrame(self.coords_frame, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=2)
        for lbl, w in [("Name", 160), ("X", 60), ("Y", 60), ("", 36)]:
            ctk.CTkLabel(header, text=lbl, width=w, font=("", 11, "bold"), text_color=TEXT_DIM).pack(side="left", padx=2)
        for name, data in coords.items():
            row = ctk.CTkFrame(self.coords_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            ctk.CTkLabel(row, text=name, width=160, anchor="w", text_color=TEXT, font=("", 11)).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=str(data.get("x", "")), width=60, text_color=TEXT_DIM, font=("", 11)).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=str(data.get("y", "")), width=60, text_color=TEXT_DIM, font=("", 11)).pack(side="left", padx=2)
            ctk.CTkButton(
                row, text="🗑", width=28, height=24, fg_color="transparent",
                hover_color=BG_HOVER, text_color="#FF4444",
                command=lambda n=name: self._delete_coord(n),
            ).pack(side="right", padx=2)

    def _delete_coord(self, name: str):
        if messagebox.askyesno("Delete", f"Delete coordinate '{name}'?"):
            self.bot.coordinate_mapper.remove_coordinate(name)
            self._refresh_coords()

    def _prompt_for_name(self, x: int, y: int) -> Optional[str]:
        """Thread-safe prompt for a button name via CTkInputDialog on the main thread.

        Schedules the dialog on the Tk main thread and blocks the calling
        (background) thread until the user responds or until the 5-minute
        timeout expires.  Returns ``None`` if cancelled or timed out.
        """
        result_q: queue.Queue = queue.Queue()

        def _show():
            dialog = ctk.CTkInputDialog(
                text=f"Mouse at ({x}, {y})\nEnter a name for this button:",
                title="Record Coordinate",
            )
            result_q.put(dialog.get_input())

        self.winfo_toplevel().after(0, _show)
        try:
            return result_q.get(timeout=300) or None  # 5-minute safety timeout
        except queue.Empty:
            return None

    def _start_mapping(self):
        win = ctk.CTkToplevel(self)
        win.title("Coordinate Mapping")
        win.geometry("420x210")
        win.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(
            win,
            text=(
                "Coordinate Mapping Mode\n\n"
                "Press F2 to record the current mouse position.\n"
                "A dialog will ask for the button name.\n"
                "Press F3 to save the current session and continue.\n"
                "Press Escape to finish."
            ),
            justify="left", text_color=TEXT,
        ).pack(padx=20, pady=20)

        def run():
            win.after(500, win.destroy)
            threading.Thread(
                target=self.bot.start_coordinate_mapping,
                kwargs={"prompt_callback": self._prompt_for_name},
                daemon=True,
            ).start()

        ctk.CTkButton(
            win, text="Start", command=run,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#000000",
        ).pack(pady=8)

    def _calibrate(self):
        win = ctk.CTkToplevel(self)
        win.title("Troop Bar Calibration")
        win.geometry("420x200")
        win.configure(fg_color=BG_MAIN)
        ctk.CTkLabel(
            win,
            text=(
                "Troop Bar Calibration\n\n"
                "1. Make sure Clash of Clans is visible.\n"
                "2. Press F2 to start calibration.\n"
                "3. Click the leftmost then rightmost troop slot."
            ),
            justify="left", text_color=TEXT,
        ).pack(padx=20, pady=20)
        ctk.CTkButton(
            win, text="Close", command=win.destroy,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT,
        ).pack(pady=8)

    def _export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if path:
            self.bot.coordinate_mapper.export_coordinates(path)
            messagebox.showinfo("Exported", f"Coordinates exported to:\n{path}")

    def _import(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.bot.coordinate_mapper.import_coordinates(path)
            self._refresh_coords()
            messagebox.showinfo("Imported", "Coordinates imported successfully.")

    def on_show(self):
        self._refresh_coords()


# ---------------------------------------------------------------------------
# Settings page
# ---------------------------------------------------------------------------

class SettingsPage(ctk.CTkFrame):
    """Configuration page for bot settings."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent, fg_color=BG_MAIN)
        self.bot = bot_controller
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # --- Anti-Ban (left column) ---
        ab_frame = _make_section(self, "Anti-Ban")
        ab_frame.grid(row=0, column=0, padx=(12, 6), pady=(12, 6), sticky="nsew")
        ab_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(ab_frame, text="Enable:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=4, sticky="e"
        )
        self.ab_switch = ctk.CTkSwitch(
            ab_frame, text="", width=46, height=24,
            progress_color=ACCENT, button_color=TEXT,
        )
        self.ab_switch.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(ab_frame, text="Click offset (px):", text_color=TEXT_DIM, font=("", 11)).grid(
            row=2, column=0, padx=8, pady=4, sticky="e"
        )
        self.offset_label = ctk.CTkLabel(ab_frame, text="5", width=28, text_color=TEXT, font=("", 11))
        self.offset_label.grid(row=2, column=1, padx=(8, 0), pady=4, sticky="w")
        self.offset_slider = ctk.CTkSlider(
            ab_frame, from_=1, to=15, number_of_steps=14,
            command=lambda v: self.offset_label.configure(text=str(int(v))),
            width=140, progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_H,
        )
        self.offset_slider.grid(row=3, column=0, columnspan=2, padx=8, pady=(0, 4), sticky="ew")

        ctk.CTkLabel(ab_frame, text="Delay variance:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=4, column=0, padx=8, pady=4, sticky="e"
        )
        self.variance_label = ctk.CTkLabel(ab_frame, text="0.3", width=34, text_color=TEXT, font=("", 11))
        self.variance_label.grid(row=4, column=1, padx=(8, 0), pady=4, sticky="w")
        self.variance_slider = ctk.CTkSlider(
            ab_frame, from_=0.1, to=0.5, number_of_steps=8,
            command=lambda v: self.variance_label.configure(text=f"{v:.1f}"),
            width=140, progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_H,
        )
        self.variance_slider.grid(row=5, column=0, columnspan=2, padx=8, pady=(0, 4), sticky="ew")

        ctk.CTkLabel(ab_frame, text="Cooldown min (s):", text_color=TEXT_DIM, font=("", 11)).grid(
            row=6, column=0, padx=8, pady=4, sticky="e"
        )
        self.cd_min_entry = ctk.CTkEntry(
            ab_frame, width=70, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.cd_min_entry.grid(row=6, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(ab_frame, text="Cooldown max (s):", text_color=TEXT_DIM, font=("", 11)).grid(
            row=7, column=0, padx=8, pady=4, sticky="e"
        )
        self.cd_max_entry = ctk.CTkEntry(
            ab_frame, width=70, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.cd_max_entry.grid(row=7, column=1, padx=8, pady=(4, 2), sticky="w")

        ctk.CTkLabel(ab_frame, text="Max attacks/hour:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=8, column=0, padx=8, pady=4, sticky="e"
        )
        self.max_aph_entry = ctk.CTkEntry(
            ab_frame, width=70, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.max_aph_entry.grid(row=8, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(ab_frame, text="Break every N:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=9, column=0, padx=8, pady=(4, 8), sticky="e"
        )
        self.break_n_entry = ctk.CTkEntry(
            ab_frame, width=70, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.break_n_entry.grid(row=9, column=1, padx=8, pady=(4, 8), sticky="w")

        # --- AI Settings (right column) ---
        ai_frame = _make_section(self, "AI Settings")
        ai_frame.grid(row=0, column=1, padx=(6, 12), pady=(12, 6), sticky="nsew")
        ai_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(ai_frame, text="API Key:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=4, sticky="e"
        )
        self.settings_api_key_entry = ctk.CTkEntry(
            ai_frame, placeholder_text="Gemini API key", show="*", width=180, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.settings_api_key_entry.grid(row=1, column=1, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(ai_frame, text="Model:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=2, column=0, padx=8, pady=4, sticky="e"
        )
        self.model_entry = ctk.CTkEntry(
            ai_frame, width=180, height=26,
            fg_color=BG_MAIN, border_color=BORDER, text_color=TEXT,
        )
        self.model_entry.grid(row=2, column=1, padx=8, pady=4, sticky="ew")

        ctk.CTkButton(
            ai_frame, text="Test Connection", command=self._test_ai,
            height=28, fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
        ).grid(row=3, column=0, columnspan=2, padx=8, pady=6)

        # --- Dashboard settings (right column, row 1) ---
        dash_frame = _make_section(self, "Dashboard")
        dash_frame.grid(row=1, column=1, padx=(6, 12), pady=6, sticky="nsew")
        dash_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(dash_frame, text="Show after attack:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=4, sticky="e"
        )
        self.show_dash_switch = ctk.CTkSwitch(
            dash_frame, text="", width=46, height=24,
            progress_color=ACCENT, button_color=TEXT,
        )
        self.show_dash_switch.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(dash_frame, text="Save session stats:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=2, column=0, padx=8, pady=(4, 8), sticky="e"
        )
        self.save_stats_switch = ctk.CTkSwitch(
            dash_frame, text="", width=46, height=24,
            progress_color=ACCENT, button_color=TEXT,
        )
        self.save_stats_switch.grid(row=2, column=1, padx=8, pady=(4, 8), sticky="w")

        # --- Theme (left column, row 1) ---
        theme_frame = _make_section(self, "Theme")
        theme_frame.grid(row=1, column=0, padx=(12, 6), pady=6, sticky="nsew")
        theme_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(theme_frame, text="Appearance:", text_color=TEXT_DIM, font=("", 11)).grid(
            row=1, column=0, padx=8, pady=(4, 8), sticky="e"
        )
        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=["Dark", "Light", "System"],
            command=lambda v: ctk.set_appearance_mode(v),
            width=120, height=28, fg_color=BTN_FG, button_color=BG_HOVER,
            dropdown_fg_color=BG_SECT, text_color=TEXT,
        )
        self.theme_menu.grid(row=1, column=1, padx=8, pady=(4, 8), sticky="w")

        # --- Save button ---
        ctk.CTkButton(
            self, text="💾 Save Settings", command=self._save_settings,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#000000",
            height=32, font=("", 12, "bold"),
        ).grid(row=2, column=0, columnspan=2, pady=12)

    def _load_settings(self):
        cfg = self.bot.config
        if cfg.get("anti_ban.enabled", True):
            self.ab_switch.select()
        self.offset_slider.set(cfg.get("anti_ban.click_offset_range", 5))
        self.offset_label.configure(text=str(int(cfg.get("anti_ban.click_offset_range", 5))))
        self.variance_slider.set(cfg.get("anti_ban.delay_variance", 0.3))
        self.variance_label.configure(text=f"{cfg.get('anti_ban.delay_variance', 0.3):.1f}")
        self.cd_min_entry.insert(0, str(cfg.get("anti_ban.cooldown_min", 10)))
        self.cd_max_entry.insert(0, str(cfg.get("anti_ban.cooldown_max", 45)))
        self.max_aph_entry.insert(0, str(cfg.get("anti_ban.max_attacks_per_hour", 20)))
        self.break_n_entry.insert(0, str(cfg.get("anti_ban.break_every_n_attacks", 10)))

        api = cfg.get("ai_analyzer.google_gemini_api_key", "")
        if api and api != "YOUR_GEMINI_API_KEY_HERE":
            self.settings_api_key_entry.insert(0, api)
        self.model_entry.insert(0, cfg.get("ai_analyzer.model", "gemini-2.5-flash-lite"))

        if cfg.get("dashboard.show_after_each_attack", True):
            self.show_dash_switch.select()
        if cfg.get("dashboard.save_session_stats", True):
            self.save_stats_switch.select()

    def _test_ai(self):
        api_key = self.settings_api_key_entry.get().strip()
        if api_key:
            self.bot.config.set("ai_analyzer.google_gemini_api_key", api_key)
            self.bot.ai_analyzer.api_key = api_key
        result = self.bot.test_ai_connection()
        if result:
            messagebox.showinfo("AI Test", "✅ Connection successful!")
        else:
            messagebox.showerror("AI Test", "❌ Connection failed. Check your API key and model.")

    def _save_settings(self):
        cfg = self.bot.config
        cfg.set("anti_ban.enabled", bool(self.ab_switch.get()))
        cfg.set("anti_ban.click_offset_range", int(self.offset_slider.get()))
        cfg.set("anti_ban.delay_variance", round(float(self.variance_slider.get()), 2))
        try:
            cfg.set("anti_ban.cooldown_min", int(self.cd_min_entry.get()))
            cfg.set("anti_ban.cooldown_max", int(self.cd_max_entry.get()))
            cfg.set("anti_ban.max_attacks_per_hour", int(self.max_aph_entry.get()))
            cfg.set("anti_ban.break_every_n_attacks", int(self.break_n_entry.get()))
        except ValueError:
            messagebox.showerror("Invalid Input", "Numeric fields must be integers.")
            return
        api = self.settings_api_key_entry.get().strip()
        if api:
            cfg.set("ai_analyzer.google_gemini_api_key", api)
        model = self.model_entry.get().strip()
        if model:
            cfg.set("ai_analyzer.model", model)
        cfg.set("dashboard.show_after_each_attack", bool(self.show_dash_switch.get()))
        cfg.set("dashboard.save_session_stats", bool(self.save_stats_switch.get()))
        cfg.save_config()
        messagebox.showinfo("Settings", "Settings saved successfully.")

    def on_show(self):
        pass


# ---------------------------------------------------------------------------
# Main GUI class
# ---------------------------------------------------------------------------

class BotGUI:
    """Main CustomTkinter GUI for the COC Attack Bot."""

    PAGES = [
        ("🏠", "Dashboard",   "dashboard"),
        ("⚔️",  "Auto Attack", "auto_attack"),
        ("📹", "Recording",   "recording"),
        ("▶️",  "Playback",    "playback"),
        ("🎯", "Coordinates", "coordinates"),
        ("🔧", "Settings",    "settings"),
    ]

    def __init__(self, bot_controller: BotController):
        self.bot = bot_controller

        self.root = ctk.CTk()
        self.root.title("COC Attack Bot")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(fg_color=BG_MAIN)

        self._build_layout()
        self._build_sidebar()
        self._build_pages()
        self._build_log_panel()
        self._setup_log_handler()

        # Show default page
        self.show_page("dashboard")

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build_layout(self):
        """Create the three main layout regions."""
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Sidebar - narrow icon-only strip (column 0)
        self.sidebar = ctk.CTkFrame(self.root, width=56, corner_radius=0, fg_color=BG_MAIN)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)

        # Main content + log panel (column 1)
        right_frame = ctk.CTkFrame(self.root, fg_color=BG_MAIN)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=0)

        # Content area
        self.content_frame = ctk.CTkFrame(right_frame, fg_color=BG_MAIN)
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        # Log panel (fixed height at bottom)
        self.log_frame = ctk.CTkFrame(right_frame, height=150, corner_radius=0, fg_color=BG_SECT)
        self.log_frame.grid(row=1, column=0, sticky="ew")
        self.log_frame.grid_propagate(False)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(1, weight=1)
        self._log_expanded = True

    def _build_sidebar(self):
        """Populate the sidebar with icon-only navigation buttons."""
        ctk.CTkFrame(self.sidebar, height=12, fg_color="transparent").pack()

        self._nav_buttons = {}
        for icon, _label, key in self.PAGES:
            btn = ctk.CTkButton(
                self.sidebar,
                text=icon,
                width=44,
                height=44,
                corner_radius=8,
                fg_color="transparent",
                text_color=TEXT_DIM,
                hover_color=BG_HOVER,
                font=("", 18),
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(pady=4, padx=4)
            self._nav_buttons[key] = btn

    def _build_pages(self):
        """Instantiate all page frames inside the content area."""
        self.pages: dict = {}
        page_classes = {
            "dashboard":   DashboardPage,
            "auto_attack": AutoAttackPage,
            "recording":   RecordingPage,
            "playback":    PlaybackPage,
            "coordinates": CoordinatesPage,
            "settings":    SettingsPage,
        }
        for key, cls in page_classes.items():
            page = cls(self.content_frame, self.bot)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

    def _build_log_panel(self):
        """Build the always-visible log panel at the bottom."""
        header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        header.columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="LOG", font=("", 11, "bold"), text_color=TEXT_DIM).grid(
            row=0, column=0, padx=6
        )

        self.log_filter = ctk.CTkSegmentedButton(
            header,
            values=["All", "Info", "Warning", "Error"],
            command=self._on_log_filter,
            width=260,
            fg_color=BG_MAIN,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_H,
            unselected_color=BG_MAIN,
            unselected_hover_color=BG_HOVER,
            text_color=TEXT_DIM,
            text_color_disabled=TEXT_DIM,
        )
        self.log_filter.set("All")
        self.log_filter.grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            header, text="🖥 Debug Console", width=130, height=26,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
            command=self._open_debug_console,
        ).grid(row=0, column=2, padx=4)

        ctk.CTkButton(
            header, text="🗑 Clear", width=70, height=26,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
            command=self._clear_log,
        ).grid(row=0, column=3, padx=4)

        self._log_toggle_btn = ctk.CTkButton(
            header, text="▲", width=36, height=26,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, font=("", 11),
            command=self._toggle_log_panel,
        )
        self._log_toggle_btn.grid(row=0, column=4, padx=(4, 2))

        # Log textbox
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame,
            state="disabled",
            font=("Courier", 10),
            wrap="word",
            fg_color=BG_MAIN,
            text_color=TEXT,
            border_width=0,
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 6))

        self._log_entries: list = []

    def _toggle_log_panel(self) -> None:
        """Collapse or expand the log panel."""
        if self._log_expanded:
            self.log_frame.configure(height=32)
            self.log_textbox.grid_remove()
            self._log_toggle_btn.configure(text="▼")
        else:
            self.log_frame.configure(height=150)
            self.log_textbox.grid()
            self._log_toggle_btn.configure(text="▲")
        self._log_expanded = not self._log_expanded

    def _setup_log_handler(self):
        """Connect the Logger's GUI callback to this panel."""
        self._log_handler = GUILogHandler(self.log_textbox, self.root)
        self.bot.logger.set_gui_callback(self._log_with_filter)

    def _log_with_filter(self, message: str, level: str = "INFO") -> None:
        """Store log entry and display according to active filter."""
        self._log_entries.append((level, message))
        current_filter = self.log_filter.get()
        if current_filter == "All" or current_filter.upper() == level.upper():
            self._log_handler.write(message, level)

    def _on_log_filter(self, value: str) -> None:
        """Re-render the log panel when the filter changes."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
        for level, message in self._log_entries:
            if value == "All" or value.upper() == level.upper():
                self._log_handler.write(message, level)

    def _clear_log(self):
        self._log_entries.clear()
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def _open_debug_console(self):
        """Open a separate window showing the raw log file."""
        log_path = self.bot.logger.get_log_file_path()
        win = ctk.CTkToplevel(self.root)
        win.title("Debug Console")
        win.geometry("800x500")
        win.configure(fg_color=BG_MAIN)
        tb = ctk.CTkTextbox(
            win, font=("Courier", 10), state="disabled",
            fg_color=BG_SECT, text_color=TEXT,
        )
        tb.pack(fill="both", expand=True, padx=8, pady=8)

        def _load():
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                tb.configure(state="normal")
                tb.delete("1.0", "end")
                tb.insert("end", content)
                tb.configure(state="disabled")
                tb.see("end")
            except OSError:
                tb.configure(state="normal")
                tb.insert("end", f"Could not read log file: {log_path}")
                tb.configure(state="disabled")

        _load()
        ctk.CTkButton(
            win, text="↺ Refresh", command=_load,
            fg_color=BTN_FG, hover_color=BG_HOVER, text_color=TEXT, height=28,
        ).pack(pady=4)

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def show_page(self, page_name: str) -> None:
        """Raise the selected page and update sidebar button states."""
        self.pages[page_name].tkraise()
        for key, btn in self._nav_buttons.items():
            if key == page_name:
                btn.configure(fg_color=ACCENT, text_color="#000000")
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_DIM)
        page = self.pages[page_name]
        if hasattr(page, "on_show"):
            page.on_show()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        """Clean up before closing the window."""
        self.bot.logger.set_gui_callback(None)
        self.bot.shutdown()
        self.root.destroy()
