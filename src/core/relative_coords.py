"""
Relative Coordinates - Store and resolve button coordinates as window ratios
"""

from typing import Dict, Optional, Tuple

from .coordinate_mapper import CoordinateMapper
from .screen_capture import ScreenCapture
from ..utils.logger import Logger


def absolute_to_relative(
    x: int, y: int, window: Tuple[int, int, int, int]
) -> Tuple[float, float]:
    """Convert absolute screen coordinates to relative (ratio) form.

    Args:
        x, y:   Absolute pixel coordinates.
        window: ``(win_x, win_y, win_w, win_h)`` — top-left corner and size
                of the reference window.

    Returns:
        ``(rx, ry)`` where each value is in the range 0.0–1.0.
    """
    win_x, win_y, win_w, win_h = window
    rx = (x - win_x) / win_w if win_w else 0.0
    ry = (y - win_y) / win_h if win_h else 0.0
    return (rx, ry)


def relative_to_absolute(
    rx: float, ry: float, window: Tuple[int, int, int, int]
) -> Tuple[int, int]:
    """Convert relative (ratio) coordinates back to absolute screen coordinates.

    Args:
        rx, ry: Ratio values (0.0–1.0).
        window: ``(win_x, win_y, win_w, win_h)``.

    Returns:
        ``(x, y)`` as integers.
    """
    win_x, win_y, win_w, win_h = window
    x = win_x + int(rx * win_w)
    y = win_y + int(ry * win_h)
    return (x, y)


class RelativeCoordinateMapper:
    """Wraps :class:`CoordinateMapper` so that coordinates are stored as
    window ratios (``rx``/``ry``) rather than absolute pixel positions.

    This means coordinates remain correct even after the emulator window is
    moved or resized.

    **Backward compatibility**: The mapper transparently reads coordinates
    stored in the legacy absolute format ``{"x": int, "y": int}`` and converts
    them on the fly using the current window bounds.

    Usage::

        mapper = RelativeCoordinateMapper(coordinate_mapper=cm, screen_capture=sc)
        mapper.save_relative("attack", abs_x=500, abs_y=300)
        abs_x, abs_y = mapper.get_absolute("attack")
    """

    def __init__(
        self,
        coordinate_mapper: CoordinateMapper,
        screen_capture: ScreenCapture,
        logger: Optional[Logger] = None,
    ):
        self._mapper = coordinate_mapper
        self._screen_capture = screen_capture
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_relative(self, name: str, abs_x: int, abs_y: int) -> None:
        """Convert *abs_x*/*abs_y* to relative form using the current window
        bounds and save via :class:`CoordinateMapper`.

        Falls back to saving in absolute format if the game window cannot be
        detected (preserves existing behaviour).
        """
        window = self._get_window()
        if window:
            rx, ry = absolute_to_relative(abs_x, abs_y, window)
            self._mapper.add_coordinate(name, abs_x, abs_y)
            # Overwrite with the relative format so future reads use ratios
            coords = self._mapper.get_coordinates()
            coords[name] = {"rx": rx, "ry": ry}
            self._mapper.save_coordinates(name, coords[name])
            self._log(f"Saved '{name}' as relative ({rx:.4f}, {ry:.4f})")
        else:
            self._mapper.add_coordinate(name, abs_x, abs_y)
            self._log(
                f"Saved '{name}' as absolute ({abs_x}, {abs_y}) — "
                "game window not found",
                "warning",
            )

    def get_absolute(self, name: str) -> Optional[Tuple[int, int]]:
        """Return absolute screen coordinates for *name*, resolving relative
        coords using the current window bounds if needed.

        Returns:
            ``(x, y)`` or ``None`` if the name is not mapped.
        """
        coords = self._mapper.get_coordinates()
        if name not in coords:
            return None
        entry = coords[name]
        return self._resolve(entry)

    def get_all_absolute(self) -> Dict[str, Dict[str, int]]:
        """Return all stored coordinates in absolute form.

        Returns:
            ``{"button_name": {"x": int, "y": int}, ...}``
        """
        coords = self._mapper.get_coordinates()
        result: Dict[str, Dict[str, int]] = {}
        for name, entry in coords.items():
            pos = self._resolve(entry)
            if pos is not None:
                result[name] = {"x": pos[0], "y": pos[1]}
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, entry: Dict) -> Optional[Tuple[int, int]]:
        """Resolve a coordinate entry to absolute ``(x, y)``."""
        if "rx" in entry and "ry" in entry:
            window = self._get_window()
            if window:
                return relative_to_absolute(entry["rx"], entry["ry"], window)
            # Fallback: no window available — cannot resolve relative coords
            self._log(
                "Cannot resolve relative coordinates: game window not detected",
                "warning",
            )
            return None
        if "x" in entry and "y" in entry:
            return (int(entry["x"]), int(entry["y"]))
        return None

    def _get_window(self) -> Optional[Tuple[int, int, int, int]]:
        """Return current game window bounds, detecting if not cached."""
        bounds = self._screen_capture.game_window_bounds
        if bounds:
            return bounds
        return self._screen_capture.find_game_window()

    def _log(self, msg: str, level: str = "info") -> None:
        """Route logging through the injected Logger, falling back to print."""
        if self._logger:
            getattr(self._logger, level, self._logger.info)(msg)
        else:
            print(msg)
