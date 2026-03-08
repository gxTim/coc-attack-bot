"""
Setup Wizard - Guided first-time setup for CoC Attack Bot
"""

import time
from typing import Callable, List, Optional, Tuple

import keyboard
import pyautogui

from .auto_detector import AutoDetector
from .coordinate_mapper import CoordinateMapper
from .screen_capture import ScreenCapture
from ..utils.logger import Logger

# (button_name, user_instruction_text)
_SETUP_STEPS: List[Tuple[str, str]] = [
    ("attack",                "the 'Attack' button on the main home screen"),
    ("find_a_match",          "the 'Find a Match' button in the attack lobby"),
    ("attack_confirm_button", "the green 'Attack' confirm button (new CoC update)"),
    ("next_button",           "the 'Next' button during base searching"),
    ("end_button",            "the 'End' button during base searching"),
    ("surrender_button",      "the 'Surrender' button in the battle screen"),
    ("surrender_confirm",     "the 'Surrender' confirm dialog button"),
    ("return_home",           "the 'Return Home' button after battle"),
]

# Critical buttons whose absence means setup is incomplete
_CRITICAL_BUTTONS = {"attack", "find_a_match", "next_button", "return_home"}


class SetupWizard:
    """Guides the user through first-time bot setup.

    1. Finds the game window automatically.
    2. Tries to auto-detect all buttons using :class:`AutoDetector`.
    3. For each button that wasn't auto-detected, prompts the user to hover
       over it and press F2.
    4. Saves all coordinates via :class:`CoordinateMapper`.
    5. Returns ``True`` if all critical buttons are mapped.

    Works in both console mode and GUI mode (via *progress_callback*).
    """

    def __init__(
        self,
        screen_capture: ScreenCapture,
        coordinate_mapper: CoordinateMapper,
        auto_detector: Optional[AutoDetector] = None,
        logger: Optional[Logger] = None,
    ):
        self._screen_capture = screen_capture
        self._mapper = coordinate_mapper
        self._auto_detector = auto_detector
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> bool:
        """Run the full setup wizard.

        Args:
            progress_callback: Optional ``(step, total, message)`` callable
                               for GUI progress updates.

        Returns:
            ``True`` if setup completed with all critical buttons mapped.
        """
        total_steps = len(_SETUP_STEPS)
        self._report(progress_callback, 0, total_steps, "Starting setup wizard…")

        # Step 1: Find game window
        self._log("🔍 Looking for game window…")
        bounds = self._screen_capture.find_game_window()
        if bounds:
            self._log(f"✅ Game window found at {bounds}")
        else:
            self._log(
                "⚠️  Game window not detected — make sure the emulator is running.",
                "warning",
            )

        # Step 2: Auto-detect buttons
        auto_found: dict = {}
        if self._auto_detector is not None:
            self._log("🤖 Attempting auto-detection of buttons…")
            auto_found = self._auto_detector.detect_all_buttons()
            if auto_found:
                self._log(f"✅ Auto-detected {len(auto_found)} button(s): {list(auto_found.keys())}")
            else:
                self._log("ℹ️  No buttons auto-detected — will guide you through manual mapping.")

        # Save auto-detected buttons
        for button_name, coords in auto_found.items():
            self._mapper.add_coordinate(button_name, coords["x"], coords["y"])

        # Step 3: Manual mapping for any button not auto-detected
        manually_mapped: List[str] = []
        for step_idx, (button_name, instruction) in enumerate(_SETUP_STEPS, start=1):
            self._report(
                progress_callback,
                step_idx,
                total_steps,
                f"Setting up: {button_name}",
            )

            if button_name in auto_found:
                self._log(f"  ✅ [{step_idx}/{total_steps}] '{button_name}' — auto-detected, skipping.")
                continue

            self._log(
                f"\n  📍 [{step_idx}/{total_steps}] Please navigate to {instruction}."
            )
            self._log(
                "     Hover your mouse over the button, then press F2 to record its position."
            )
            self._log("     Press ESC to skip this button.")

            pos = self._wait_for_f2_or_esc()
            if pos:
                self._mapper.add_coordinate(button_name, pos[0], pos[1])
                manually_mapped.append(button_name)
                self._log(f"  ✅ Recorded '{button_name}' at {pos}")
            else:
                self._log(f"  ⏭  Skipped '{button_name}'", "warning")

        # Step 4: Check critical buttons
        all_coords = self._mapper.get_coordinates()
        missing_critical = _CRITICAL_BUTTONS - set(all_coords.keys())
        if missing_critical:
            self._log(
                f"⚠️  Setup incomplete — missing critical buttons: {missing_critical}",
                "warning",
            )
            self._report(
                progress_callback,
                total_steps,
                total_steps,
                f"Setup incomplete — missing: {missing_critical}",
            )
            return False

        self._log(
            f"🎉 Setup complete! "
            f"{len(auto_found)} auto-detected, {len(manually_mapped)} manually mapped."
        )
        self._report(progress_callback, total_steps, total_steps, "Setup complete!")
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_f2_or_esc(self) -> Optional[Tuple[int, int]]:
        """Block until the user presses F2 (record) or ESC (skip).

        Returns:
            ``(x, y)`` if F2 was pressed, ``None`` if ESC was pressed.
        """
        while True:
            if keyboard.is_pressed("f2"):
                x, y = pyautogui.position()
                time.sleep(0.3)  # debounce
                return (x, y)
            if keyboard.is_pressed("esc"):
                time.sleep(0.3)
                return None
            time.sleep(0.05)

    @staticmethod
    def _report(
        callback: Optional[Callable[[int, int, str], None]],
        step: int,
        total: int,
        message: str,
    ) -> None:
        """Call the progress callback if provided."""
        if callback:
            callback(step, total, message)

    def _log(self, msg: str, level: str = "info") -> None:
        """Route logging through the injected Logger, falling back to print."""
        if self._logger:
            getattr(self._logger, level, self._logger.info)(msg)
        else:
            print(msg)
