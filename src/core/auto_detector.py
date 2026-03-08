"""
Auto Detector - Automatically detects standard CoC UI buttons using template matching
"""

import os
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .screen_capture import ScreenCapture
from ..utils.logger import Logger

# Scales tried during multi-scale template matching (handles different emulator resolutions)
_MATCH_SCALES = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]

# Mapping of logical button names → template filenames in templates/buttons/
BUTTON_TEMPLATES: Dict[str, str] = {
    "attack":                  "btn_attack.png",
    "find_a_match":            "btn_find_match.png",
    "attack_confirm_button":   "btn_attack_confirm.png",
    "next_button":             "btn_next.png",
    "end_button":              "btn_end.png",
    "surrender_button":        "btn_surrender.png",
    "surrender_confirm":       "btn_surrender_confirm.png",
    "return_home":             "btn_return_home.png",
}

_TEMPLATE_DIR = os.path.join("templates", "buttons")


class AutoDetector:
    """Automatically detects standard CoC UI buttons on screen using multi-scale
    OpenCV template matching.

    Usage::

        detector = AutoDetector(screen_capture=sc, logger=logger)
        pos = detector.detect_button("attack")  # returns (x, y) or None
        all_btns = detector.detect_all_buttons()  # returns CoordinateMapper-compatible dict
    """

    def __init__(self, screen_capture: ScreenCapture, logger: Optional[Logger] = None):
        self._screen_capture = screen_capture
        self._logger = logger
        # Cache: button_name → (x, y) or None
        self._cache: Dict[str, Optional[Tuple[int, int]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_button(
        self,
        button_name: str,
        threshold: float = 0.75,
        use_cache: bool = True,
    ) -> Optional[Tuple[int, int]]:
        """Detect a single button on screen.

        Args:
            button_name: One of the keys in :data:`BUTTON_TEMPLATES`.
            threshold:   Minimum match confidence (0–1).  Default 0.75.
            use_cache:   Return cached result if available.

        Returns:
            ``(x, y)`` centre coordinates or ``None`` if not found.
        """
        if use_cache and button_name in self._cache:
            return self._cache[button_name]

        if button_name not in BUTTON_TEMPLATES:
            self._log(f"Unknown button name: '{button_name}'", "warning")
            return None

        template_path = os.path.join(_TEMPLATE_DIR, BUTTON_TEMPLATES[button_name])
        if not os.path.exists(template_path):
            self._log(
                f"Template not found for '{button_name}': {template_path} — "
                "place a screenshot of the button in templates/buttons/",
                "warning",
            )
            self._cache[button_name] = None
            return None

        result = self._multi_scale_match(template_path, threshold)
        self._cache[button_name] = result
        if result:
            self._log(f"✅ Auto-detected '{button_name}' at {result}")
        else:
            self._log(f"❌ Could not auto-detect '{button_name}'", "warning")
        return result

    def detect_all_buttons(
        self, threshold: float = 0.75
    ) -> Dict[str, Dict[str, int]]:
        """Detect all known buttons and return a CoordinateMapper-compatible dict.

        Returns::

            {
                "attack":         {"x": 123, "y": 456},
                "find_a_match":   {"x": 789, "y": 321},
                ...
            }

        Buttons that could not be detected are omitted from the result.
        """
        result: Dict[str, Dict[str, int]] = {}
        for button_name in BUTTON_TEMPLATES:
            pos = self.detect_button(button_name, threshold=threshold, use_cache=False)
            if pos is not None:
                result[button_name] = {"x": pos[0], "y": pos[1]}
        self._log(
            f"Auto-detected {len(result)}/{len(BUTTON_TEMPLATES)} buttons"
        )
        return result

    def invalidate_cache(self) -> None:
        """Clear all cached detection results."""
        self._cache.clear()
        self._log("Auto-detector cache cleared")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _multi_scale_match(
        self, template_path: str, threshold: float
    ) -> Optional[Tuple[int, int]]:
        """Try template matching at multiple scales and return the best match.

        Captures the current screen (or game window region), then resizes the
        *template* at each scale in :data:`_MATCH_SCALES` and runs
        ``cv2.matchTemplate``.  The match with the highest confidence above
        *threshold* wins.

        Returns:
            ``(x, y)`` coordinates in screen space or ``None``.
        """
        # Capture the current screen as a PIL Image (no disk I/O)
        screenshot_pil = self._screen_capture._capture_raw()
        if screenshot_pil is None:
            self._log("_capture_raw() returned None — cannot run auto-detection", "error")
            return None

        screenshot_cv = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)

        # Load the template from disk
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            self._log(f"Failed to load template image: {template_path}", "error")
            return None

        best_val = -1.0
        best_x = 0
        best_y = 0
        best_tw = 0
        best_th = 0

        orig_h, orig_w = template.shape[:2]

        for scale in _MATCH_SCALES:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))

            # Skip scales where the template would be larger than the screenshot
            scr_h, scr_w = screenshot_cv.shape[:2]
            if new_h > scr_h or new_w > scr_w:
                continue

            resized = cv2.resize(template, (new_w, new_h))
            result = cv2.matchTemplate(screenshot_cv, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val = max_val
                best_x, best_y = max_loc
                best_tw = new_w
                best_th = new_h

        if best_val < threshold:
            return None

        # Return the centre of the best match
        center_x = best_x + best_tw // 2
        center_y = best_y + best_th // 2

        # Adjust for game-window offset if a region was used
        bounds = self._screen_capture.game_window_bounds
        if bounds:
            center_x += bounds[0]
            center_y += bounds[1]

        return (center_x, center_y)

    def _log(self, msg: str, level: str = "info") -> None:
        """Route logging through the injected Logger, falling back to print."""
        if self._logger:
            getattr(self._logger, level, self._logger.info)(msg)
        else:
            print(msg)
