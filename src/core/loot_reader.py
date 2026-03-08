"""
Loot Reader - Local OCR-based loot value extraction from screenshots
"""

import re
from typing import Dict, Optional, Tuple

from ..utils.logger import Logger

# Loot display regions as ratios of the game window (x_ratio, y_ratio, w_ratio, h_ratio)
# These cover the typical position of gold/elixir/dark elixir counters on the base-preview screen.
_DEFAULT_LOOT_REGIONS: Dict[str, Tuple[float, float, float, float]] = {
    "gold":        (0.02, 0.06, 0.25, 0.06),
    "elixir":      (0.02, 0.13, 0.25, 0.06),
    "dark_elixir": (0.02, 0.20, 0.25, 0.06),
}

# Upscale factor applied before OCR to improve digit recognition
_OCR_SCALE = 2


class LootReader:
    """Reads Gold, Elixir, and Dark Elixir values from a CoC base-preview screenshot
    using local OCR (``easyocr`` or ``pytesseract``).

    Both OCR engines are optional; the class gracefully degrades if neither is
    installed, allowing the caller to fall back to AI-based loot checking.

    Usage::

        reader = LootReader(logger=logger)
        loot = reader.read_loot_from_screenshot("screenshots/base.png", game_bounds=(0, 0, 1920, 1080))
        # → {"gold": 500000, "elixir": 450000, "dark_elixir": 3000}
    """

    def __init__(self, logger: Optional[Logger] = None):
        self._logger = logger
        self._easyocr_reader = None
        self._pytesseract = None
        self._engine: Optional[str] = None

        # Try to load an OCR engine
        self._engine = self._detect_engine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """Return True if at least one OCR engine is available."""
        return self._engine is not None

    def read_loot_from_screenshot(
        self,
        screenshot_path: str,
        game_bounds: Optional[Tuple[int, int, int, int]] = None,
        region_overrides: Optional[Dict[str, Tuple[float, float, float, float]]] = None,
    ) -> Dict[str, int]:
        """Extract loot values from a screenshot file.

        Args:
            screenshot_path:  Path to the base-preview screenshot.
            game_bounds:      ``(x, y, width, height)`` of the game window in
                              screen coordinates.  Used to convert ratio-based
                              region definitions to absolute pixel regions.
                              If ``None``, the full screenshot is used and
                              ratios are applied to its own dimensions.
            region_overrides: Optional dict overriding the default region
                              ratios per resource type.

        Returns:
            ``{"gold": int, "elixir": int, "dark_elixir": int}`` — any
            unreadable value is 0.
        """
        from PIL import Image  # Pillow is a hard dependency

        if not self.is_available:
            self._log(
                "⚠️ No OCR engine available (install easyocr or pytesseract). "
                "Returning zeros.",
                "warning",
            )
            return {"gold": 0, "elixir": 0, "dark_elixir": 0}

        try:
            img = Image.open(screenshot_path)
        except Exception as exc:
            self._log(f"Failed to open screenshot '{screenshot_path}': {exc}", "error")
            return {"gold": 0, "elixir": 0, "dark_elixir": 0}

        img_w, img_h = img.size
        # If game_bounds provided, use its dimensions for ratio conversion; else
        # use the image dimensions directly.
        ref_w = game_bounds[2] if game_bounds else img_w
        ref_h = game_bounds[3] if game_bounds else img_h

        regions = region_overrides if region_overrides else _DEFAULT_LOOT_REGIONS

        result: Dict[str, int] = {"gold": 0, "elixir": 0, "dark_elixir": 0}
        for key in result:
            if key not in regions:
                continue
            rx, ry, rw, rh = regions[key]
            # Convert ratios to pixel coords relative to the image
            px = int(rx * ref_w)
            py = int(ry * ref_h)
            pw = int(rw * ref_w)
            ph = int(rh * ref_h)

            # Crop from the full screenshot (no offset needed — screenshot is
            # already cropped to the game window, so coordinates start at 0)
            crop = img.crop((px, py, px + pw, py + ph))
            processed = self._preprocess_for_ocr(crop)
            text = self._run_ocr(processed)
            value = self._parse_number(text)
            result[key] = value
            self._log(f"OCR '{key}': raw='{text}' → {value}")

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_engine(self) -> Optional[str]:
        """Try to import available OCR engines; return the name of the first
        one that loads successfully."""
        try:
            import easyocr  # type: ignore
            self._easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._log("OCR engine: easyocr")
            return "easyocr"
        except ImportError:
            pass
        except Exception as exc:
            self._log(f"easyocr available but failed to init: {exc}", "warning")

        try:
            import pytesseract  # type: ignore
            # Quick sanity check
            pytesseract.get_tesseract_version()
            self._pytesseract = pytesseract
            self._log("OCR engine: pytesseract")
            return "pytesseract"
        except (ImportError, Exception):
            pass

        self._log(
            "No OCR engine found. Install 'easyocr' or 'pytesseract' for local loot reading.",
            "warning",
        )
        return None

    def _preprocess_for_ocr(self, img):
        """Convert to grayscale, apply adaptive threshold, and scale up 2×.

        Args:
            img: PIL Image (any mode).

        Returns:
            Processed PIL Image.
        """
        import cv2
        import numpy as np
        from PIL import Image

        cv_img = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)

        # Adaptive threshold to enhance digit contrast
        cv_img = cv2.adaptiveThreshold(
            cv_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Scale up for better OCR accuracy
        new_w = cv_img.shape[1] * _OCR_SCALE
        new_h = cv_img.shape[0] * _OCR_SCALE
        cv_img = cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        return Image.fromarray(cv_img)

    def _run_ocr(self, img) -> str:
        """Run the active OCR engine on a preprocessed PIL Image."""
        import numpy as np

        if self._engine == "easyocr" and self._easyocr_reader is not None:
            detections = self._easyocr_reader.readtext(
                np.array(img), detail=0, paragraph=True
            )
            return " ".join(detections)

        if self._engine == "pytesseract" and self._pytesseract is not None:
            return self._pytesseract.image_to_string(
                img,
                config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,. ",
            )

        return ""

    def _parse_number(self, text: str) -> int:
        """Extract an integer from OCR text, handling commas, dots, and spaces.

        Examples::

            "500,000" → 500000
            "1.250.000" → 1250000
            "3 000" → 3000
            "abc" → 0
        """
        # Remove everything that isn't a digit, comma, dot, or space
        cleaned = re.sub(r"[^\d,.\s]", "", text)
        # Remove separators (commas, dots used as thousands separators, spaces)
        digits_only = re.sub(r"[,.\s]", "", cleaned)
        if not digits_only:
            return 0
        try:
            return int(digits_only)
        except ValueError:
            return 0

    def _log(self, msg: str, level: str = "info") -> None:
        """Route logging through the injected Logger, falling back to print."""
        if self._logger:
            getattr(self._logger, level, self._logger.info)(msg)
        else:
            print(msg)
