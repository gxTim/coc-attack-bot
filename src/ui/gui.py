"""
GUI - CustomTkinter-based graphical user interface for the COC Attack Bot
"""

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
# Log handler
# ---------------------------------------------------------------------------

class GUILogHandler:
    """Routes log messages to the GUI log panel in a thread-safe manner."""

    # Color tags used in the log textbox
    LEVEL_COLOURS = {
        "INFO": "white",
        "WARNING": "#FFA500",
        "ERROR": "#FF4444",
        "CRITICAL": "#FF0000",
        "SUCCESS": "#44FF88",
        "LOOT": "#44DDFF",
    }

    def __init__(self, log_textbox: ctk.CTkTextbox, root: ctk.CTk):
        self.log_textbox = log_textbox
        self.root = root

    def write(self, message: str, level: str = "INFO") -> None:
        """Thread-safe log writing to the GUI panel."""
        def _append():
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", f"[{ts}] [{level}] {message}\n")
                self.log_textbox.configure(state="disabled")
                self.log_textbox.see("end")
            except Exception:
                pass  # Window may have been destroyed

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
        super().__init__(parent)
        self.bot = bot_controller
        self._polling = False
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        # Title
        ctk.CTkLabel(self, text="Dashboard", font=("", 20, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(16, 8), sticky="ew"
        )

        # Status indicator
        self.status_label = ctk.CTkLabel(
            self, text="IDLE", font=("", 28, "bold"), text_color="gray"
        )
        self.status_label.grid(row=1, column=0, columnspan=3, pady=(4, 12))

        # Loot cards
        loot_frame = ctk.CTkFrame(self)
        loot_frame.grid(row=2, column=0, columnspan=3, padx=16, pady=8, sticky="ew")
        loot_frame.columnconfigure((0, 1, 2), weight=1)

        self.gold_label = ctk.CTkLabel(loot_frame, text="💰 Gold\n0", font=("", 14))
        self.gold_label.grid(row=0, column=0, padx=12, pady=8)

        self.elixir_label = ctk.CTkLabel(loot_frame, text="💧 Elixir\n0", font=("", 14))
        self.elixir_label.grid(row=0, column=1, padx=12, pady=8)

        self.dark_label = ctk.CTkLabel(loot_frame, text="⚫ Dark Elixir\n0", font=("", 14))
        self.dark_label.grid(row=0, column=2, padx=12, pady=8)

        # Attack stats
        stats_frame = ctk.CTkFrame(self)
        stats_frame.grid(row=3, column=0, columnspan=3, padx=16, pady=8, sticky="ew")
        stats_frame.columnconfigure((0, 1), weight=1)

        self.attacks_label = ctk.CTkLabel(stats_frame, text="Attacks: 0  |  Success: 0%", font=("", 13))
        self.attacks_label.grid(row=0, column=0, columnspan=2, pady=4)

        self.rate_label = ctk.CTkLabel(stats_frame, text="Attacks/hour: 0", font=("", 13))
        self.rate_label.grid(row=1, column=0, pady=4)

        self.runtime_label = ctk.CTkLabel(stats_frame, text="Runtime: 0h 0m", font=("", 13))
        self.runtime_label.grid(row=1, column=1, pady=4)

        self.last_attack_label = ctk.CTkLabel(stats_frame, text="Last attack: —", font=("", 13))
        self.last_attack_label.grid(row=2, column=0, columnspan=2, pady=4)

    def on_show(self):
        """Called when this page is raised; starts the polling loop."""
        if not self._polling:
            self._polling = True
            self.update_stats()

    def update_stats(self):
        """Periodically refresh dashboard statistics."""
        try:
            if self.bot.is_auto_attacking():
                stats = self.bot.get_auto_attack_stats()
                self.status_label.configure(text="RUNNING", text_color="green")

                total = stats.get("total_attacks", 0)
                success_rate = stats.get("success_rate", 0.0)
                aph = stats.get("attacks_per_hour", 0.0)
                runtime_h = stats.get("runtime_hours", 0.0)
                last = stats.get("last_attack", "—")

                h = int(runtime_h)
                m = int((runtime_h - h) * 60)

                self.attacks_label.configure(
                    text=f"Attacks: {total}  |  Success: {success_rate:.1f}%"
                )
                self.rate_label.configure(text=f"Attacks/hour: {aph:.1f}")
                self.runtime_label.configure(text=f"Runtime: {h}h {m}m")
                self.last_attack_label.configure(text=f"Last attack: {last}")
            else:
                self.status_label.configure(text="STOPPED", text_color="red")
        except Exception:
            pass

        self.after(2000, self.update_stats)


# ---------------------------------------------------------------------------
# Auto Attack page
# ---------------------------------------------------------------------------

class AutoAttackPage(ctk.CTkFrame):
    """Configuration and control page for the automated attack system."""

    def __init__(self, parent, bot_controller: BotController):
        super().__init__(parent)
        self.bot = bot_controller
        self._session_vars: dict = {}
        self._build_ui()
        self._refresh_sessions()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Auto Attack", font=("", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(16, 8)
        )

        # --- Session list ---
        self.sessions_frame = ctk.CTkScrollableFrame(self, label_text="Attack Sessions", height=160)
        self.sessions_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=8, sticky="ew")

        ctk.CTkButton(
            self, text="↺ Refresh Sessions", command=self._refresh_sessions, width=140
        ).grid(row=2, column=0, columnspan=2, pady=4)

        # --- Loot requirements ---
        loot_frame = ctk.CTkFrame(self)
        loot_frame.grid(row=3, column=0, columnspan=2, padx=16, pady=8, sticky="ew")
        loot_frame.columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        ctk.CTkLabel(loot_frame, text="Min Gold:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.gold_entry = ctk.CTkEntry(loot_frame, placeholder_text="300000", width=100)
        self.gold_entry.grid(row=0, column=1, padx=6, pady=6)

        ctk.CTkLabel(loot_frame, text="Min Elixir:").grid(row=0, column=2, padx=6, pady=6, sticky="e")
        self.elixir_entry = ctk.CTkEntry(loot_frame, placeholder_text="300000", width=100)
        self.elixir_entry.grid(row=0, column=3, padx=6, pady=6)

        ctk.CTkLabel(loot_frame, text="Min Dark:").grid(row=0, column=4, padx=6, pady=6, sticky="e")
        self.dark_entry = ctk.CTkEntry(loot_frame, placeholder_text="2000", width=100)
        self.dark_entry.grid(row=0, column=5, padx=6, pady=6)

        # --- TH Level ---
        th_frame = ctk.CTkFrame(self)
        th_frame.grid(row=4, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        ctk.CTkLabel(th_frame, text="Max TH Level:").grid(row=0, column=0, padx=8, pady=6)
        self.th_dropdown = ctk.CTkOptionMenu(th_frame, values=[str(i) for i in range(1, 17)], width=80)
        self.th_dropdown.set("16")
        self.th_dropdown.grid(row=0, column=1, padx=8, pady=6)

        # --- AI toggle ---
        ai_frame = ctk.CTkFrame(self)
        ai_frame.grid(row=5, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        ctk.CTkLabel(ai_frame, text="AI Analysis:").grid(row=0, column=0, padx=8, pady=6)
        self.ai_switch = ctk.CTkSwitch(ai_frame, text="")
        self.ai_switch.grid(row=0, column=1, padx=8, pady=6)
        ctk.CTkLabel(ai_frame, text="Gemini API Key:").grid(row=0, column=2, padx=8, pady=6)
        self.api_key_entry = ctk.CTkEntry(ai_frame, placeholder_text="API key", show="*", width=180)
        self.api_key_entry.grid(row=0, column=3, padx=8, pady=6)

        # --- Troop bar calibration ---
        ctk.CTkButton(
            self, text="🎯 Calibrate Troop Bar", command=self._calibrate_troop_bar
        ).grid(row=6, column=0, columnspan=2, pady=6)

        # --- Start / Stop ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=7, column=0, columnspan=2, pady=12)

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶ Start Auto Attack", fg_color="green",
            width=180, command=self._start_attack
        )
        self.start_btn.grid(row=0, column=0, padx=12)

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="⏹ Stop", fg_color="red",
            width=120, command=self._stop_attack, state="disabled"
        )
        self.stop_btn.grid(row=0, column=1, padx=12)

        self._load_config_values()

    def _load_config_values(self):
        """Pre-fill fields from existing config."""
        cfg = self.bot.config
        self.gold_entry.delete(0, "end")
        self.gold_entry.insert(0, str(cfg.get("ai_analyzer.min_gold", 300000)))
        self.elixir_entry.delete(0, "end")
        self.elixir_entry.insert(0, str(cfg.get("ai_analyzer.min_elixir", 300000)))
        self.dark_entry.delete(0, "end")
        self.dark_entry.insert(0, str(cfg.get("ai_analyzer.min_dark_elixir", 2000)))
        th = cfg.get("auto_attacker.max_th_level", 16)
        self.th_dropdown.set(str(th))
        if cfg.get("ai_analyzer.enabled", False):
            self.ai_switch.select()
        api = cfg.get("ai_analyzer.google_gemini_api_key", "")
        if api and api != "YOUR_GEMINI_API_KEY_HERE":
            self.api_key_entry.delete(0, "end")
            self.api_key_entry.insert(0, api)

    def _refresh_sessions(self):
        """Reload the session checkboxes from disk."""
        for widget in self.sessions_frame.winfo_children():
            widget.destroy()
        self._session_vars = {}
        sessions = self.bot.list_recorded_attacks()
        if not sessions:
            ctk.CTkLabel(self.sessions_frame, text="No recordings found.").pack(padx=8, pady=4)
        for name in sessions:
            var = tk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(self.sessions_frame, text=name, variable=var)
            cb.pack(anchor="w", padx=8, pady=2)
            self._session_vars[name] = var

    def _calibrate_troop_bar(self):
        win = ctk.CTkToplevel(self)
        win.title("Troop Bar Calibration")
        win.geometry("420x220")
        ctk.CTkLabel(
            win,
            text=(
                "Troop Bar Calibration\n\n"
                "1. Make sure Clash of Clans is visible on screen.\n"
                "2. Press F2 to begin calibration.\n"
                "3. Click the leftmost troop slot, then the rightmost.\n"
                "4. The bot will save the calibration automatically."
            ),
            justify="left",
        ).pack(padx=20, pady=20)
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)

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

        # Update AI config
        ai_enabled = self.ai_switch.get()
        self.bot.config.set("ai_analyzer.enabled", bool(ai_enabled))
        api_key = self.api_key_entry.get().strip()
        if api_key:
            self.bot.config.set("ai_analyzer.google_gemini_api_key", api_key)
        th = int(self.th_dropdown.get())
        self.bot.config.set("auto_attacker.max_th_level", th)

        threading.Thread(
            target=self.bot.start_auto_attack,
            args=(selected, min_gold, min_elixir, min_dark),
            daemon=True,
        ).start()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def _stop_attack(self):
        threading.Thread(target=self.bot.stop_auto_attack, daemon=True).start()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def on_show(self):
        self._refresh_sessions()
        # Sync button states
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
        super().__init__(parent)
        self.bot = bot_controller
        self._recording_start: Optional[float] = None
        self._build_ui()
        self._refresh_recordings()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Attack Recording", font=("", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(16, 8)
        )

        # Session name
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        ctk.CTkLabel(name_frame, text="Session name:").pack(side="left", padx=6)
        self.name_entry = ctk.CTkEntry(name_frame, placeholder_text="e.g. goblin_barch", width=200)
        self.name_entry.pack(side="left", padx=6)

        # Auto-detect toggle
        detect_frame = ctk.CTkFrame(self, fg_color="transparent")
        detect_frame.grid(row=2, column=0, columnspan=2, padx=16, pady=4, sticky="ew")
        ctk.CTkLabel(detect_frame, text="Auto-detect clicks:").pack(side="left", padx=6)
        self.detect_switch = ctk.CTkSwitch(detect_frame, text="")
        self.detect_switch.select()
        self.detect_switch.pack(side="left", padx=6)

        # Record button
        self.record_btn = ctk.CTkButton(
            self, text="⏺ Start Recording", fg_color="red", command=self._toggle_recording
        )
        self.record_btn.grid(row=3, column=0, columnspan=2, pady=8)

        # Status
        self.rec_status = ctk.CTkLabel(self, text="", text_color="orange")
        self.rec_status.grid(row=4, column=0, columnspan=2)

        # Recordings list
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Recordings", height=220)
        self.list_frame.grid(row=5, column=0, columnspan=2, padx=16, pady=8, sticky="ew")

        ctk.CTkButton(self, text="↺ Refresh", command=self._refresh_recordings, width=100).grid(
            row=6, column=0, columnspan=2, pady=4
        )

    def _toggle_recording(self):
        if not self.bot.is_recording:
            name = self.name_entry.get().strip()
            if not name:
                messagebox.showwarning("No Name", "Please enter a session name.")
                return
            self.bot.start_attack_recording(name)
            self._recording_start = time.time()
            self.record_btn.configure(text="⏹ Stop Recording", fg_color="gray")
            self._update_rec_status()
        else:
            self.bot.stop_attack_recording()
            self._recording_start = None
            self.record_btn.configure(text="⏺ Start Recording", fg_color="red")
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
            ctk.CTkLabel(self.list_frame, text="No recordings yet.").pack(padx=8, pady=4)
            return
        for name in sessions:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(row, text=name, width=200, anchor="w").pack(side="left", padx=4)
            # Show info if available
            info = self.bot.attack_recorder.get_recording_info(name)
            if info:
                actions = info.get("action_count", 0)
                dur = info.get("duration", 0.0)
                ctk.CTkLabel(row, text=f"{actions} actions  {dur:.1f}s", text_color="gray").pack(
                    side="left", padx=8
                )
            del_btn = ctk.CTkButton(
                row, text="🗑", width=32, fg_color="transparent",
                command=lambda n=name: self._delete_recording(n)
            )
            del_btn.pack(side="right", padx=4)

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
        super().__init__(parent)
        self.bot = bot_controller
        self._play_thread: Optional[threading.Thread] = None
        self._build_ui()
        self._refresh_sessions()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Attack Playback", font=("", 20, "bold")).grid(
            row=0, column=0, pady=(16, 8)
        )

        # Session selector
        sel_frame = ctk.CTkFrame(self, fg_color="transparent")
        sel_frame.grid(row=1, column=0, padx=16, pady=6, sticky="ew")
        ctk.CTkLabel(sel_frame, text="Session:").pack(side="left", padx=6)
        self.session_menu = ctk.CTkOptionMenu(sel_frame, values=["(none)"], width=220)
        self.session_menu.pack(side="left", padx=6)
        ctk.CTkButton(sel_frame, text="↺", width=32, command=self._refresh_sessions).pack(
            side="left", padx=4
        )

        # Speed control
        speed_frame = ctk.CTkFrame(self, fg_color="transparent")
        speed_frame.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        ctk.CTkLabel(speed_frame, text="Speed:").pack(side="left", padx=6)
        self.speed_label = ctk.CTkLabel(speed_frame, text="1.0×", width=40)
        self.speed_label.pack(side="left", padx=4)
        self.speed_slider = ctk.CTkSlider(
            speed_frame, from_=0.1, to=5.0, number_of_steps=49,
            command=self._on_speed_change, width=200
        )
        self.speed_slider.set(1.0)
        self.speed_slider.pack(side="left", padx=6)

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, width=400)
        self.progress.set(0)
        self.progress.grid(row=3, column=0, padx=16, pady=8)

        # Status
        self.pb_status = ctk.CTkLabel(self, text="Stopped")
        self.pb_status.grid(row=4, column=0)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=5, column=0, pady=12)
        self.play_btn = ctk.CTkButton(
            btn_frame, text="▶ Play", fg_color="green", width=120, command=self._play
        )
        self.play_btn.grid(row=0, column=0, padx=8)
        self.stop_pb_btn = ctk.CTkButton(
            btn_frame, text="⏹ Stop", fg_color="red", width=80,
            command=self._stop_playback, state="disabled"
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
        super().__init__(parent)
        self.bot = bot_controller
        self._build_ui()
        self._refresh_coords()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Coordinates", font=("", 20, "bold")).grid(
            row=0, column=0, pady=(16, 8)
        )

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=6)
        ctk.CTkButton(btn_frame, text="▶ Start Mapping", command=self._start_mapping).grid(
            row=0, column=0, padx=8
        )
        ctk.CTkButton(btn_frame, text="🎯 Calibrate Troop Bar", command=self._calibrate).grid(
            row=0, column=1, padx=8
        )
        ctk.CTkButton(btn_frame, text="📤 Export", command=self._export).grid(row=0, column=2, padx=8)
        ctk.CTkButton(btn_frame, text="📥 Import", command=self._import).grid(row=0, column=3, padx=8)

        self.coords_frame = ctk.CTkScrollableFrame(self, label_text="Mapped Coordinates", height=300)
        self.coords_frame.grid(row=2, column=0, padx=16, pady=8, sticky="ew")

        ctk.CTkButton(self, text="↺ Refresh", command=self._refresh_coords, width=100).grid(
            row=3, column=0, pady=4
        )

    def _refresh_coords(self):
        for widget in self.coords_frame.winfo_children():
            widget.destroy()
        coords = self.bot.get_mapped_coordinates()
        if not coords:
            ctk.CTkLabel(self.coords_frame, text="No coordinates mapped yet.").pack(padx=8, pady=4)
            return
        # Header row
        header = ctk.CTkFrame(self.coords_frame, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=2)
        for text, w in [("Name", 160), ("X", 60), ("Y", 60), ("", 40)]:
            ctk.CTkLabel(header, text=text, width=w, font=("", 12, "bold")).pack(side="left", padx=2)
        for name, data in coords.items():
            row = ctk.CTkFrame(self.coords_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            ctk.CTkLabel(row, text=name, width=160, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text=str(data.get("x", "")), width=60).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=str(data.get("y", "")), width=60).pack(side="left", padx=2)
            ctk.CTkButton(
                row, text="🗑", width=32, fg_color="transparent",
                command=lambda n=name: self._delete_coord(n)
            ).pack(side="right", padx=2)

    def _delete_coord(self, name: str):
        if messagebox.askyesno("Delete", f"Delete coordinate '{name}'?"):
            self.bot.coordinate_mapper.remove_coordinate(name)
            self._refresh_coords()

    def _start_mapping(self):
        win = ctk.CTkToplevel(self)
        win.title("Coordinate Mapping")
        win.geometry("400x200")
        ctk.CTkLabel(
            win,
            text=(
                "Coordinate Mapping Mode\n\n"
                "Press F2 to start mapping.\n"
                "Hover over each button and press F2 to record its position.\n"
                "Press Escape to finish."
            ),
            justify="left",
        ).pack(padx=20, pady=20)

        def run():
            win.after(500, win.destroy)
            threading.Thread(target=self.bot.start_coordinate_mapping, daemon=True).start()

        ctk.CTkButton(win, text="Start", command=run).pack(pady=8)

    def _calibrate(self):
        win = ctk.CTkToplevel(self)
        win.title("Troop Bar Calibration")
        win.geometry("420x200")
        ctk.CTkLabel(
            win,
            text=(
                "Troop Bar Calibration\n\n"
                "1. Make sure Clash of Clans is visible.\n"
                "2. Press F2 to start calibration.\n"
                "3. Click the leftmost then rightmost troop slot."
            ),
            justify="left",
        ).pack(padx=20, pady=20)
        ctk.CTkButton(win, text="Close", command=win.destroy).pack(pady=8)

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
        super().__init__(parent)
        self.bot = bot_controller
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Settings", font=("", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(16, 8)
        )

        # --- Anti-Ban ---
        ab_frame = ctk.CTkFrame(self, border_width=1)
        ab_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=8, sticky="ew")
        ab_frame.columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(ab_frame, text="Anti-Ban", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=4, padx=8, pady=4, sticky="w"
        )
        ctk.CTkLabel(ab_frame, text="Enable:").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self.ab_switch = ctk.CTkSwitch(ab_frame, text="")
        self.ab_switch.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        ctk.CTkLabel(ab_frame, text="Click offset (px):").grid(row=2, column=0, padx=8, pady=4, sticky="e")
        self.offset_label = ctk.CTkLabel(ab_frame, text="5", width=30)
        self.offset_label.grid(row=2, column=1, padx=2)
        self.offset_slider = ctk.CTkSlider(
            ab_frame, from_=1, to=15, number_of_steps=14,
            command=lambda v: self.offset_label.configure(text=str(int(v))), width=160
        )
        self.offset_slider.grid(row=2, column=2, columnspan=2, padx=8, pady=4)

        ctk.CTkLabel(ab_frame, text="Delay variance:").grid(row=3, column=0, padx=8, pady=4, sticky="e")
        self.variance_label = ctk.CTkLabel(ab_frame, text="0.3", width=36)
        self.variance_label.grid(row=3, column=1, padx=2)
        self.variance_slider = ctk.CTkSlider(
            ab_frame, from_=0.1, to=0.5, number_of_steps=8,
            command=lambda v: self.variance_label.configure(text=f"{v:.1f}"), width=160
        )
        self.variance_slider.grid(row=3, column=2, columnspan=2, padx=8, pady=4)

        ctk.CTkLabel(ab_frame, text="Cooldown min (s):").grid(row=4, column=0, padx=8, pady=4, sticky="e")
        self.cd_min_entry = ctk.CTkEntry(ab_frame, width=70)
        self.cd_min_entry.grid(row=4, column=1, padx=8, pady=4)
        ctk.CTkLabel(ab_frame, text="max (s):").grid(row=4, column=2, padx=8, pady=4, sticky="e")
        self.cd_max_entry = ctk.CTkEntry(ab_frame, width=70)
        self.cd_max_entry.grid(row=4, column=3, padx=8, pady=4)

        ctk.CTkLabel(ab_frame, text="Max attacks/hour:").grid(row=5, column=0, padx=8, pady=4, sticky="e")
        self.max_aph_entry = ctk.CTkEntry(ab_frame, width=70)
        self.max_aph_entry.grid(row=5, column=1, padx=8, pady=4)
        ctk.CTkLabel(ab_frame, text="Break every N attacks:").grid(row=5, column=2, padx=8, pady=4, sticky="e")
        self.break_n_entry = ctk.CTkEntry(ab_frame, width=70)
        self.break_n_entry.grid(row=5, column=3, padx=8, pady=4)

        # --- AI Settings ---
        ai_frame = ctk.CTkFrame(self, border_width=1)
        ai_frame.grid(row=2, column=0, columnspan=2, padx=16, pady=8, sticky="ew")
        ai_frame.columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(ai_frame, text="AI Settings", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=4, padx=8, pady=4, sticky="w"
        )
        ctk.CTkLabel(ai_frame, text="API Key:").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self.settings_api_key_entry = ctk.CTkEntry(ai_frame, placeholder_text="Gemini API key", show="*", width=200)
        self.settings_api_key_entry.grid(row=1, column=1, columnspan=2, padx=8, pady=4, sticky="ew")
        ctk.CTkLabel(ai_frame, text="Model:").grid(row=2, column=0, padx=8, pady=4, sticky="e")
        self.model_entry = ctk.CTkEntry(ai_frame, width=200)
        self.model_entry.grid(row=2, column=1, columnspan=2, padx=8, pady=4, sticky="ew")
        ctk.CTkButton(ai_frame, text="Test Connection", command=self._test_ai).grid(
            row=3, column=1, columnspan=2, padx=8, pady=6
        )

        # --- Dashboard settings ---
        dash_frame = ctk.CTkFrame(self, border_width=1)
        dash_frame.grid(row=3, column=0, columnspan=2, padx=16, pady=8, sticky="ew")
        ctk.CTkLabel(dash_frame, text="Dashboard", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=4, padx=8, pady=4, sticky="w"
        )
        ctk.CTkLabel(dash_frame, text="Show after each attack:").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self.show_dash_switch = ctk.CTkSwitch(dash_frame, text="")
        self.show_dash_switch.grid(row=1, column=1, padx=8, pady=4, sticky="w")
        ctk.CTkLabel(dash_frame, text="Save session stats:").grid(row=2, column=0, padx=8, pady=4, sticky="e")
        self.save_stats_switch = ctk.CTkSwitch(dash_frame, text="")
        self.save_stats_switch.grid(row=2, column=1, padx=8, pady=4, sticky="w")

        # --- Theme ---
        theme_frame = ctk.CTkFrame(self, fg_color="transparent")
        theme_frame.grid(row=4, column=0, columnspan=2, padx=16, pady=6, sticky="ew")
        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left", padx=8)
        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=["Dark", "Light", "System"],
            command=lambda v: ctk.set_appearance_mode(v), width=120
        )
        self.theme_menu.pack(side="left", padx=8)

        # Save button
        ctk.CTkButton(self, text="💾 Save Settings", command=self._save_settings).grid(
            row=5, column=0, columnspan=2, pady=12
        )

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
        ("🏠", "Dashboard", "dashboard"),
        ("⚔️", "Auto Attack", "auto_attack"),
        ("📹", "Recording", "recording"),
        ("▶️", "Playback", "playback"),
        ("🎯", "Coordinates", "coordinates"),
        ("🔧", "Settings", "settings"),
    ]

    def __init__(self, bot_controller: BotController):
        self.bot = bot_controller

        self.root = ctk.CTk()
        self.root.title("COC Attack Bot")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

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

        # Sidebar (column 0)
        self.sidebar = ctk.CTkFrame(self.root, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)

        # Main content + log panel (column 1)
        right_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=0)

        # Content area
        self.content_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

        # Log panel (fixed height at bottom)
        self.log_frame = ctk.CTkFrame(right_frame, height=200, corner_radius=0)
        self.log_frame.grid(row=1, column=0, sticky="ew")
        self.log_frame.grid_propagate(False)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(1, weight=1)

    def _build_sidebar(self):
        """Populate the sidebar with navigation buttons."""
        ctk.CTkLabel(
            self.sidebar, text="COC Bot", font=("", 18, "bold")
        ).pack(pady=(20, 12), padx=16)

        self._nav_buttons = {}
        for icon, label, key in self.PAGES:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"{icon}  {label}",
                anchor="w",
                corner_radius=6,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray30"),
                command=lambda k=key: self.show_page(k),
                width=180,
                height=36,
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_buttons[key] = btn

    def _build_pages(self):
        """Instantiate all page frames inside the content area."""
        self.pages: dict = {}
        page_classes = {
            "dashboard": DashboardPage,
            "auto_attack": AutoAttackPage,
            "recording": RecordingPage,
            "playback": PlaybackPage,
            "coordinates": CoordinatesPage,
            "settings": SettingsPage,
        }
        for key, cls in page_classes.items():
            page = cls(self.content_frame, self.bot)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

    def _build_log_panel(self):
        """Build the always-visible log panel at the bottom."""
        # Header row with title and filter
        header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        header.columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="Log", font=("", 13, "bold")).grid(row=0, column=0, padx=4)

        self.log_filter = ctk.CTkSegmentedButton(
            header,
            values=["All", "Info", "Warning", "Error"],
            command=self._on_log_filter,
            width=260,
        )
        self.log_filter.set("All")
        self.log_filter.grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            header, text="🖥 Debug Console", width=130,
            command=self._open_debug_console
        ).grid(row=0, column=2, padx=4)

        ctk.CTkButton(
            header, text="🗑 Clear", width=70,
            command=self._clear_log
        ).grid(row=0, column=3, padx=4)

        # Log textbox
        self.log_textbox = ctk.CTkTextbox(
            self.log_frame, state="disabled", font=("Courier", 11), wrap="word"
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 6))

        self._log_entries: list = []  # (level, text) tuples for filtering

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
        tb = ctk.CTkTextbox(win, font=("Courier", 11), state="disabled")
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
        ctk.CTkButton(win, text="↺ Refresh", command=_load).pack(pady=4)

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def show_page(self, page_name: str) -> None:
        """Raise the selected page and update sidebar button states."""
        self.pages[page_name].tkraise()
        # Update nav button highlight
        for key, btn in self._nav_buttons.items():
            if key == page_name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")
        # Notify the page it became visible
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
