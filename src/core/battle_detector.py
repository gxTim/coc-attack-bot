"""
Battle Detector - Multi-method battle-end detection for CoC
"""

import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .screen_capture import ScreenCapture
from ..utils.logger import Logger

# HSV range for the distinctive gold/yellow star colour that appears after battle
_STAR_HUE_LOW    = 20
_STAR_HUE_HIGH   = 35
_STAR_SAT_LOW    = 150
_STAR_SAT_HIGH   = 255
_STAR_VAL_LOW    = 200
_STAR_VAL_HIGH   = 255

# Fraction of the star region that must contain the star colour before we declare stars visible
_STAR_PIXEL_RATIO = 0.05

# Default star region as ratios (win_x_ratio, win_y_ratio, win_w_ratio, win_h_ratio)
# Top-centre area where CoC victory stars appear
_DEFAULT_STAR_REGION: Tuple[float, float, float, float] = (0.35, 0.05, 0.30, 0.15)


class BattleEndDetector:
    """Detects the end of a CoC battle using multiple complementary methods:

    1. **Template matching** for ``battle_end.png`` / ``return_home.png``.
    2. **Star overlay detection** — identifies the gold/yellow victory stars
       that appear at the top of the screen after battle by analysing HSV colour.

    Usage::

        detector = BattleEndDetector(screen_capture=sc, logger=logger)
        reason = detector.check_battle_end(
            templates=[("templates/battle_end.png", "battle_end")],
        )
        # reason is "template", "stars", or None (still ongoing)
    """

    def __init__(
        self,
        screen_capture: ScreenCapture,
        logger: Optional[Logger] = None,
    ):
        self._screen_capture = screen_capture
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_battle_end(
        self,
        templates: Optional[List[Tuple[str, str]]] = None,
        star_region: Optional[Tuple[float, float, float, float]] = None,
    ) -> Optional[str]:
        """Run all detection methods in a single pass.

        Args:
            templates:   List of ``(template_path, name)`` tuples.  Each path
                         is matched against the current screen.
            star_region: ``(rx, ry, rw, rh)`` ratios defining where to look
                         for victory stars.  Falls back to :data:`_DEFAULT_STAR_REGION`.

        Returns:
            * ``"template"`` — a battle-end template was found on screen.
            * ``"stars"``    — the gold-star overlay was detected.
            * ``None``       — battle appears to still be ongoing.
        """
        # --- Method 1: template matching ---
        if templates:
            for template_path, name in templates:
                match = self._screen_capture.find_template_on_screen(
                    template_path, threshold=0.8
                )
                if match:
                    self._log(f"🏁 Battle end detected via template ({name})")
                    return "template"

        # --- Method 2: star overlay detection ---
        region_ratios = star_region if star_region else _DEFAULT_STAR_REGION
        star_found = self._detect_stars(region_ratios)
        if star_found:
            self._log("🏁 Battle end detected via star overlay")
            return "stars"

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_stars(self, region_ratios: Tuple[float, float, float, float]) -> bool:
        """Return True if the gold-star overlay is visible in the star region.

        Captures the star region (as defined by *region_ratios* applied to the
        game window bounds, or the full screen), converts to HSV, and checks
        whether at least :data:`_STAR_PIXEL_RATIO` of pixels fall in the
        gold-yellow range.
        """
        rx, ry, rw, rh = region_ratios
        region = self._ratio_to_pixels(rx, ry, rw, rh)

        screenshot = self._screen_capture._capture_raw(region=region)
        if screenshot is None:
            return False

        hsv = cv2.cvtColor(np.array(screenshot.convert("RGB")), cv2.COLOR_RGB2HSV)

        lower = np.array([_STAR_HUE_LOW, _STAR_SAT_LOW, _STAR_VAL_LOW])
        upper = np.array([_STAR_HUE_HIGH, _STAR_SAT_HIGH, _STAR_VAL_HIGH])
        mask = cv2.inRange(hsv, lower, upper)

        total_pixels = mask.size
        star_pixels = int(np.sum(mask > 0))
        ratio = star_pixels / total_pixels if total_pixels > 0 else 0.0

        self._log(
            f"Star detection: {star_pixels}/{total_pixels} pixels "
            f"({ratio * 100:.1f}%) in gold-yellow range"
        )
        return ratio >= _STAR_PIXEL_RATIO

    def _ratio_to_pixels(
        self,
        rx: float,
        ry: float,
        rw: float,
        rh: float,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Convert ratio-based region to absolute pixel region.

        Returns ``(x, y, width, height)`` or ``None`` if the game window is
        not available (caller then uses the full screen).
        """
        bounds = self._screen_capture.game_window_bounds
        if not bounds:
            bounds = self._screen_capture.find_game_window()
        if not bounds:
            return None

        win_x, win_y, win_w, win_h = bounds
        x = win_x + int(rx * win_w)
        y = win_y + int(ry * win_h)
        w = int(rw * win_w)
        h = int(rh * win_h)
        return (x, y, w, h)

    def _log(self, msg: str, level: str = "info") -> None:
        """Route logging through the injected Logger, falling back to print."""
        if self._logger:
            getattr(self._logger, level, self._logger.info)(msg)
        else:
            print(msg)
