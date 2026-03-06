"""
Humanizer - Utilities to make automation look more human-like (anti-ban)
"""

import random


def humanize_click(x: int, y: int, offset_range: int = 5):
    """Add small random offset to click coordinates to appear more human.

    Args:
        x: Original x coordinate.
        y: Original y coordinate.
        offset_range: Maximum pixels to offset in either direction (default 5).

    Returns:
        Tuple (x + offset_x, y + offset_y) with random offsets applied.
    """
    offset_x = random.randint(-offset_range, offset_range)
    offset_y = random.randint(-offset_range, offset_range)
    return x + offset_x, y + offset_y


def humanize_delay(base_delay: float, variance: float = 0.3) -> float:
    """Add random variance to a delay duration to appear more human.

    Args:
        base_delay: The nominal delay in seconds.
        variance: Fractional variance (0.3 means ±30%).  Defaults to 0.3.

    Returns:
        A random float in the range
        [base_delay*(1-variance), base_delay*(1+variance)].
    """
    min_delay = base_delay * (1 - variance)
    max_delay = base_delay * (1 + variance)
    return random.uniform(min_delay, max_delay)
