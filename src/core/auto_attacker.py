"""
Auto Attacker - Automated continuous attack system for COC
"""

import os
import json
import time
import random
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pyautogui
import keyboard

from .attack_player import AttackPlayer
from .screen_capture import ScreenCapture
from .coordinate_mapper import CoordinateMapper
from .ai_analyzer import AIAnalyzer
from ..utils.logger import Logger
from ..utils.config import Config
from ..utils.humanizer import humanize_click, humanize_delay

# Template images used for battle-end detection.
# Place either or both in the `templates/` directory for early battle-end detection.
_BATTLE_END_TEMPLATE = os.path.join("templates", "battle_end.png")
_RETURN_HOME_TEMPLATE = os.path.join("templates", "return_home.png")

# Pixel-colour change threshold used by the return_home heuristic detector.
# A cumulative RGB-channel delta above this value is considered a significant
# colour change indicating that the "Return Home" button has appeared.
# Raised from 30 → 50 to reduce false positives from minor pixel fluctuations.
_PIXEL_COLOR_DIFF_THRESHOLD = 50

# Number of consecutive poll cycles that must show a colour change before the
# battle is declared finished.  Requiring multiple confirmations prevents brief
# pixel fluctuations (e.g. animations) from triggering a false positive.
_PIXEL_CONFIRM_REQUIRED = 2

# Minimum seconds elapsed before the pixel-colour heuristic will declare the
# battle finished.  This prevents false positives caused by brief colour
# changes that can occur at the very start of the battle.
_MIN_BATTLE_ELAPSED_SECS = 30

# Seconds in one hour — used for hourly attack rate limiting.
_SECONDS_PER_HOUR = 3600


class AutoAttacker:
    """Automated continuous attack system"""
    
    def __init__(self, attack_player: AttackPlayer, screen_capture: ScreenCapture, 
                 coordinate_mapper: CoordinateMapper, logger: Logger, ai_analyzer: AIAnalyzer, config: Config):
        self.attack_player = attack_player
        self.screen_capture = screen_capture
        self.coordinate_mapper = coordinate_mapper
        self.logger = logger
        self.ai_analyzer = ai_analyzer
        self.config = config
        
        self.is_running = False
        self.auto_thread = None
        self._stats_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self.stats = {
            'total_attacks': 0,
            'successful_attacks': 0,
            'failed_attacks': 0,
            'start_time': None,
            'last_attack_time': None,
            'total_gold_farmed': 0,
            'total_elixir_farmed': 0,
            'total_dark_farmed': 0,
            'best_attack_loot': 0,
            'best_attack_number': 0,
            'attacks_this_hour': 0,
            'hour_start_time': None,
        }
        
        self.attack_sessions = self.config.get('auto_attacker.attack_sessions', [])
        self.max_search_attempts = self.config.get('auto_attacker.max_search_attempts', 10)
        self.current_session_index = 0
        
        # Cached coordinates (invalidated on each attack cycle)
        self._cached_coords = None
        # Last AI analysis result — updated by _check_loot_with_ai when attack is recommended
        self._last_ai_analysis: Optional[Dict] = None
        
        print("Auto Attacker initialized")
        print("Emergency stop: Ctrl+Alt+S")
    
    def add_attack_session(self, session_name: str) -> bool:
        """Add an attack session to rotation"""
        sessions = self.config.get('auto_attacker.attack_sessions', [])
        if session_name not in sessions:
            sessions.append(session_name)
            self.config.set('auto_attacker.attack_sessions', sessions)
            self.attack_sessions = sessions
            self.logger.info(f"Added attack session: {session_name}")
            return True
        return False
    
    def remove_attack_session(self, session_name: str) -> bool:
        """Remove an attack session from rotation"""
        sessions = self.config.get('auto_attacker.attack_sessions', [])
        if session_name in sessions:
            sessions.remove(session_name)
            self.config.set('auto_attacker.attack_sessions', sessions)
            self.attack_sessions = sessions
            self.logger.info(f"Removed attack session: {session_name}")
            return True
        return False
    
    def start_auto_attack(self) -> None:
        """Start the automated attack system"""
        with self._start_lock:
            if self.is_running:
                print("Auto attacker already running")
                return

            if not self.attack_sessions:
                self.logger.error("No attack sessions configured. Please add at least one session.")
                return

            self.is_running = True
            self.stats['start_time'] = datetime.now()
            self.stats['hour_start_time'] = datetime.now()
            self.stats['attacks_this_hour'] = 0

            self.auto_thread = threading.Thread(target=self._auto_attack_loop)
            self.auto_thread.daemon = True
            self.auto_thread.start()

        self.logger.info("Auto attacker started")
    
    def stop_auto_attack(self) -> None:
        """Stop the automated attack system"""
        if not self.is_running:
            return
        
        self.logger.info("Auto attacker stopping...")
        self.is_running = False
        
        # Stop any playing attack
        self.attack_player.stop_playback()
        
        if self.auto_thread and self.auto_thread.is_alive():
            self.auto_thread.join(timeout=5)
        
        self._print_session_summary()
        self._save_session_stats()
        self.logger.info("Auto attacker stopped")
    
    def _get_coords(self) -> Dict:
        """Return cached coordinates, refreshing once per attack cycle."""
        if self._cached_coords is None:
            self._cached_coords = self.coordinate_mapper.get_coordinates()
        return self._cached_coords

    def _auto_attack_loop(self) -> None:
        """Main automation loop"""
        try:
            # Anti-ban config — session-level values read once (others re-read per cycle)
            anti_ban_enabled = self.config.get('anti_ban.enabled', True)
            max_attacks_per_hour = self.config.get('anti_ban.max_attacks_per_hour', 20)
            max_attacks_per_session = self.config.get('anti_ban.max_attacks_per_session', 100)
            break_every_n = self.config.get('anti_ban.break_every_n_attacks', 10)
            break_duration_min = self.config.get('anti_ban.break_duration_min', 120)
            break_duration_max = self.config.get('anti_ban.break_duration_max', 300)

            while self.is_running:
                # Check emergency stop
                if keyboard.is_pressed('ctrl+alt+s'):
                    self.logger.warning("Emergency stop activated!")
                    break

                # Refresh coordinate cache at start of each cycle
                self._cached_coords = None

                with self._stats_lock:
                    total = self.stats['total_attacks']
                    attacks_this_hour = self.stats['attacks_this_hour']
                    hour_start = self.stats['hour_start_time']

                # ── Anti-ban: session limit ──────────────────────────────────
                if anti_ban_enabled and total >= max_attacks_per_session:
                    self.logger.warning(
                        f"🛑 Session attack limit reached ({max_attacks_per_session}). "
                        f"Stopping auto-attack."
                    )
                    break

                # ── Anti-ban: hourly limit ───────────────────────────────────
                if anti_ban_enabled and hour_start is not None:
                    elapsed_hour = (datetime.now() - hour_start).total_seconds()
                    if elapsed_hour >= _SECONDS_PER_HOUR:
                        # New hour — reset counter
                        with self._stats_lock:
                            self.stats['attacks_this_hour'] = 0
                            self.stats['hour_start_time'] = datetime.now()
                        attacks_this_hour = 0
                    elif attacks_this_hour >= max_attacks_per_hour:
                        wait_secs = int(_SECONDS_PER_HOUR - elapsed_hour)
                        self.logger.warning(
                            f"⏳ Hourly attack limit reached ({max_attacks_per_hour}/hr). "
                            f"Pausing for {wait_secs // 60}m {wait_secs % 60}s..."
                        )
                        pause_end = time.time() + wait_secs
                        while self.is_running and time.time() < pause_end:
                            time.sleep(5)
                        with self._stats_lock:
                            self.stats['attacks_this_hour'] = 0
                            self.stats['hour_start_time'] = datetime.now()

                # ── Anti-ban: activity break ─────────────────────────────────
                if anti_ban_enabled and total > 0 and break_every_n > 0 and total % break_every_n == 0:
                    break_duration = random.uniform(break_duration_min, break_duration_max)
                    self.logger.info(
                        f"☕ Activity break every {break_every_n} attacks: "
                        f"resting for {break_duration:.0f}s ({break_duration / 60:.1f} min)..."
                    )
                    break_end = time.time() + break_duration
                    while self.is_running and time.time() < break_end:
                        time.sleep(5)

                self.logger.info("🎯 Starting new attack cycle...")

                # Execute attack sequence
                self._last_ai_analysis = None
                attack_result = self._execute_attack_sequence()
                if attack_result is True:
                    with self._stats_lock:
                        self.stats['total_attacks'] += 1
                        self.stats['successful_attacks'] += 1
                        self.stats['attacks_this_hour'] += 1
                        self.stats['last_attack_time'] = datetime.now()
                        # Accumulate loot from AI analysis
                        if self._last_ai_analysis:
                            loot = self._last_ai_analysis.get('loot', {})
                            gold = loot.get('gold', 0)
                            elixir = loot.get('elixir', 0)
                            dark = loot.get('dark_elixir', 0)
                            self.stats['total_gold_farmed'] += gold
                            self.stats['total_elixir_farmed'] += elixir
                            self.stats['total_dark_farmed'] += dark
                            total_loot = gold + elixir
                            if total_loot > self.stats['best_attack_loot']:
                                self.stats['best_attack_loot'] = total_loot
                                self.stats['best_attack_number'] = self.stats['total_attacks']
                    self.logger.info("✅ Attack sequence completed successfully")
                elif attack_result is False:
                    # Attack was launched but failed (battle error, not a search failure)
                    with self._stats_lock:
                        self.stats['total_attacks'] += 1
                        self.stats['failed_attacks'] += 1
                        self.stats['last_attack_time'] = datetime.now()
                    self.logger.warning("❌ Attack sequence failed")
                else:
                    # attack_result is None — no suitable base found; don't count as an attack
                    self.logger.warning("⚠️ No suitable base found — skipping attack count")

                # Print dashboard after each cycle
                show_dashboard = self.config.get('dashboard.show_after_each_attack', True)
                if show_dashboard:
                    self._print_dashboard()

                # ── Anti-ban: cooldown before next attack ────────────────────
                if self.is_running:
                    if anti_ban_enabled:
                        # Re-read cooldown bounds each cycle so runtime config changes
                        # take effect immediately.
                        cooldown_min = self.config.get('anti_ban.cooldown_min', 10)
                        cooldown_max = self.config.get('anti_ban.cooldown_max', 45)
                        cooldown = random.uniform(cooldown_min, cooldown_max)
                        # Apply ±10% jitter so the delay visibly varies even when
                        # min and max are close together.
                        jitter = cooldown * random.uniform(-0.1, 0.1)
                        cooldown = max(1.0, cooldown + jitter)
                        self.logger.info(
                            f"😴 Anti-ban cooldown: waiting {cooldown:.1f}s before next attack..."
                        )
                    else:
                        cooldown = random.uniform(5, 15)
                        self.logger.info(f"⏳ Waiting {cooldown:.1f}s before next attack...")
                    cooldown_end = time.time() + cooldown
                    while self.is_running and time.time() < cooldown_end:
                        time.sleep(0.5)

        except Exception as e:
            self.logger.error(f"Auto attack loop error: {e}")
        finally:
            self.is_running = False
    
    def _execute_attack_sequence(self) -> Optional[bool]:
        """Execute the complete attack sequence following your exact process.

        Returns:
            True  — attack was launched and completed successfully.
            False — attack was launched but failed (battle error).
            None  — no suitable base found; no attack was launched.
        """
        try:
            coords = self._get_coords()
            delay_variance = self.config.get('anti_ban.delay_variance', 0.3)
            click_offset = self.config.get('anti_ban.click_offset_range', 5)

            # Step 1: Click attack button
            if 'attack' not in coords:
                self.logger.error("Attack button not mapped")
                return None

            if not self.is_running:
                return None

            attack_coord = coords['attack']
            self.logger.info(f"1️⃣ Clicking attack button at ({attack_coord['x']}, {attack_coord['y']})")
            hx, hy = humanize_click(attack_coord['x'], attack_coord['y'], click_offset)
            pyautogui.click(hx, hy)
            time.sleep(humanize_delay(2.0, delay_variance))

            if not self.is_running:
                return None

            # Step 2-6: Find good loot target
            if not self._find_good_loot_target():
                self.logger.warning("Could not find good loot target")
                return None

            if not self.is_running:
                return None

            # Step 7: Select attack session (AI strategy selection or rotation)
            screenshot_path = self.screen_capture.capture_game_screen()
            session_name = self._select_best_strategy(screenshot_path)
            self.logger.info(f"🎯 Starting attack with session: {session_name}")

            # Capture pixel at return_home BEFORE playback starts so that
            # battle-end detection can compare against the pre-battle state.
            initial_battle_pixel = None
            if 'return_home' in coords:
                home_coord = coords['return_home']
                initial_battle_pixel = self.screen_capture.get_pixel_color(
                    home_coord['x'], home_coord['y']
                )

            if not self.attack_player.play_attack(session_name, speed=1.0, auto_mode=True):
                self.logger.error("Failed to start attack recording")
                return False

            self.logger.info("✅ Attack recording started - troops deploying...")

            # Step 8: Wait for battle completion (detect end instead of fixed 3 min)
            self._wait_for_battle_end(initial_battle_pixel=initial_battle_pixel)

            # Step 9: Return home
            self._return_home()

            return True

        except Exception as e:
            self.logger.error(f"Attack sequence failed: {e}")
            return False
    
    def _wait_for_battle_end(self, initial_battle_pixel=None) -> None:
        """Wait for battle to end by checking for battle-end indicators.

        Detection priority:
        1. ``templates/battle_end.png`` – template match on screen.
        2. ``templates/return_home.png`` – template match on screen.
        3. ``return_home`` coordinate – pixel-colour change heuristic.
        4. Fixed timeout (configurable via ``auto_attacker.battle_timeout``).

        The method also waits for the playback thread to finish first so that
        troop deployment is complete before we start polling (fixes race
        condition between playback and battle-end detection).

        Args:
            initial_battle_pixel: RGB tuple captured at the ``return_home``
                coordinate BEFORE playback started.  When provided, this gives a
                reliable pre-battle baseline so a colour change can be detected
                immediately after playback finishes (handles the case where CoC
                auto-returns the player to the home base during troop deployment).
        """
        battle_timeout = self.config.get('auto_attacker.battle_timeout', 180)
        poll_interval = 3  # seconds between screen checks

        # Step 1: Wait for troop deployment (playback) to finish.
        if (self.attack_player.playback_thread
                and self.attack_player.playback_thread.is_alive()):
            self.logger.info("⏳ Waiting for troop deployment to complete...")
            self.attack_player.playback_thread.join(timeout=battle_timeout)

        # Step 2: Determine which templates are available.
        has_battle_end = os.path.exists(_BATTLE_END_TEMPLATE)
        has_return_home_tmpl = os.path.exists(_RETURN_HOME_TEMPLATE)

        if has_battle_end or has_return_home_tmpl:
            templates = []
            if has_battle_end:
                templates.append((_BATTLE_END_TEMPLATE, "battle_end"))
            if has_return_home_tmpl:
                templates.append((_RETURN_HOME_TEMPLATE, "return_home"))
            template_names = ", ".join(name for _, name in templates)
            self.logger.info(
                f"⏳ Waiting for battle to end (polling for: {template_names})..."
            )
            # Immediate post-playback check: battle may have ended during deployment.
            for path, name in templates:
                match = self.screen_capture.find_template_on_screen(
                    path, threshold=0.8
                )
                if match:
                    self.logger.info(
                        f"🏁 Battle already ended during deployment ({name} detected)"
                    )
                    return
            elapsed = 0
            while elapsed < battle_timeout and self.is_running:
                for path, name in templates:
                    match = self.screen_capture.find_template_on_screen(
                        path, threshold=0.8
                    )
                    if match:
                        self.logger.info(
                            f"🏁 Battle ended after ~{elapsed}s ({name} detected)"
                        )
                        return
                remaining = battle_timeout - elapsed
                self.logger.info(
                    f"⏳ Battle in progress... ~{remaining // 60}m {remaining % 60}s remaining"
                )
                time.sleep(poll_interval)
                elapsed += poll_interval
            self.logger.info(f"⏳ Battle timeout reached ({battle_timeout}s)")
            return

        # Step 3: No templates – try pixel-colour check at the return_home button.
        coords = self._get_coords()
        if 'return_home' in coords:
            home_coord = coords['return_home']
            self.logger.info(
                f"⏳ Polling for battle end using return_home pixel check at "
                f"({home_coord['x']}, {home_coord['y']}) — "
                f"for better detection place a template at "
                f"'{_RETURN_HOME_TEMPLATE}' or '{_BATTLE_END_TEMPLATE}'..."
            )
            # Use the pre-battle pixel captured before playback when available so
            # that a colour change is detectable even if the battle ended while
            # troops were still being deployed.
            if initial_battle_pixel is not None:
                initial_color = initial_battle_pixel
            else:
                initial_color = self.screen_capture.get_pixel_color(
                    home_coord['x'], home_coord['y']
                )
            # Immediate post-playback check (only meaningful with pre-captured pixel).
            if initial_battle_pixel is not None:
                # Require _PIXEL_CONFIRM_REQUIRED consecutive reads above the
                # threshold to avoid false positives from single-frame glitches.
                immediate_confirm = 0
                for _chk in range(_PIXEL_CONFIRM_REQUIRED):
                    current_color = self.screen_capture.get_pixel_color(
                        home_coord['x'], home_coord['y']
                    )
                    color_diff = sum(
                        abs(current_color[i] - initial_color[i]) for i in range(3)
                    )
                    if color_diff > _PIXEL_COLOR_DIFF_THRESHOLD:
                        immediate_confirm += 1
                    else:
                        break
                    time.sleep(0.5)
                if immediate_confirm >= _PIXEL_CONFIRM_REQUIRED:
                    self.logger.info(
                        "🏁 Battle already ended during troop deployment!"
                    )
                    return
            pixel_confirm_count = 0
            elapsed = 0
            while elapsed < battle_timeout and self.is_running:
                current_color = self.screen_capture.get_pixel_color(
                    home_coord['x'], home_coord['y']
                )
                color_diff = sum(
                    abs(current_color[i] - initial_color[i]) for i in range(3)
                )
                if initial_battle_pixel is not None:
                    # Pre-captured pixel — colour change alone is sufficient; no
                    # minimum elapsed time needed because the baseline was taken
                    # before the battle started.
                    if color_diff > _PIXEL_COLOR_DIFF_THRESHOLD:
                        pixel_confirm_count += 1
                        if pixel_confirm_count >= _PIXEL_CONFIRM_REQUIRED:
                            self.logger.info(
                                f"🏁 Battle ended after ~{elapsed}s "
                                f"(pixel colour change at return_home confirmed)"
                            )
                            return
                    else:
                        pixel_confirm_count = 0
                else:
                    # Pixel captured after playback — require minimum elapsed time
                    # to avoid false positives from brief colour changes at battle start.
                    if color_diff > _PIXEL_COLOR_DIFF_THRESHOLD and elapsed >= _MIN_BATTLE_ELAPSED_SECS:
                        pixel_confirm_count += 1
                        if pixel_confirm_count >= _PIXEL_CONFIRM_REQUIRED:
                            self.logger.info(
                                f"🏁 Battle ended after ~{elapsed}s "
                                f"(pixel colour change at return_home confirmed)"
                            )
                            return
                    else:
                        pixel_confirm_count = 0
                remaining = battle_timeout - elapsed
                self.logger.info(
                    f"⏳ Battle in progress... {remaining // 60}m {remaining % 60}s remaining"
                )
                time.sleep(poll_interval)
                elapsed += poll_interval
            self.logger.info(f"⏳ Battle timeout reached ({battle_timeout}s)")
            return

        # Step 4: Absolute fallback – no templates and no coordinate mapped.
        self.logger.warning(
            f"⚠️ No battle-end templates or return_home coordinate found. "
            f"Falling back to {battle_timeout}s wait. "
            f"Place a template at '{_RETURN_HOME_TEMPLATE}' or "
            f"'{_BATTLE_END_TEMPLATE}' for early battle-end detection."
        )
        elapsed = 0
        while elapsed < battle_timeout and self.is_running:
            remaining = battle_timeout - elapsed
            self.logger.info(
                f"⏳ Battle in progress... {remaining // 60}m {remaining % 60}s remaining"
            )
            time.sleep(poll_interval)
            elapsed += poll_interval

    def _click_attack_confirm_button(self) -> bool:
        """Click the green attack confirm button that appears after find_a_match (new CoC update)"""
        coords = self._get_coords()
        delay_variance = self.config.get('anti_ban.delay_variance', 0.3)
        click_offset = self.config.get('anti_ban.click_offset_range', 5)
        
        if 'attack_confirm_button' not in coords:
            self.logger.error("attack_confirm_button not mapped - this button is required since the latest CoC update")
            return False
        
        confirm_coord = coords['attack_confirm_button']
        self.logger.info(f"⚔️ Clicking attack_confirm_button at ({confirm_coord['x']}, {confirm_coord['y']})")
        hx, hy = humanize_click(confirm_coord['x'], confirm_coord['y'], click_offset)
        pyautogui.click(hx, hy)
        time.sleep(humanize_delay(3.0, delay_variance))
        return True

    def _find_good_loot_target(self) -> bool:
        """Find target with good loot following exact process"""
        coords = self._get_coords()
        
        for required in ('find_a_match', 'attack_confirm_button', 'next_button'):
            if required not in coords:
                self.logger.error(f"{required} button not mapped")
                return False
        
        # Try up to two full search cycles (second cycle after clicking end button)
        for cycle in range(2):
            if not self.is_running:
                return False

            if cycle > 0:
                self.logger.info("🔄 No good bases found - clicking end button to restart search...")
                self._click_end_button_and_retry()
                self.logger.info("🔄 Retrying base search after end button...")

            if self._search_bases_cycle(coords):
                return True
        
        return False

    def _search_bases_cycle(self, coords: Dict) -> bool:
        """Perform one complete cycle of base searching."""
        max_attempts = self.max_search_attempts
        delay_variance = self.config.get('anti_ban.delay_variance', 0.3)
        click_offset = self.config.get('anti_ban.click_offset_range', 5)
        
        for attempt in range(1, max_attempts + 1):
            if not self.is_running:
                return False
            
            if attempt == 1:
                # First attempt: open matchmaking and confirm.
                find_coord = coords['find_a_match']
                self.logger.info(
                    f"2️⃣ Clicking find_a_match at ({find_coord['x']}, {find_coord['y']}) "
                    f"- Attempt {attempt}/{max_attempts}"
                )
                hx, hy = humanize_click(find_coord['x'], find_coord['y'], click_offset)
                pyautogui.click(hx, hy)
                time.sleep(humanize_delay(2.0, delay_variance))

                if not self.is_running:
                    return False

                # Click the green attack confirm button (new CoC update)
                if not self._click_attack_confirm_button():
                    self.logger.error("Failed to click attack confirm button")
                    return False
            else:
                # Subsequent attempts: already in the base-browsing view,
                # so just click Next to see the next available base.
                self.logger.info(
                    f"2️⃣ Skipping to next base - Attempt {attempt}/{max_attempts}"
                )
                next_coord = coords['next_button']
                hx, hy = humanize_click(next_coord['x'], next_coord['y'], click_offset)
                pyautogui.click(hx, hy)
                time.sleep(humanize_delay(3.0, delay_variance))

            if not self.is_running:
                return False

            # Wait for base to load
            self.logger.info("3️⃣ Waiting for base to load...")
            time.sleep(humanize_delay(5.0, delay_variance))

            if not self.is_running:
                return False

            # Check loot
            screenshot_path = self.screen_capture.capture_game_screen()
            if not screenshot_path:
                self.logger.warning("Could not take screenshot, skipping base...")
                continue
            
            use_ai = self.config.get('ai_analyzer.enabled', False)
            self.logger.info(f"AI Analysis is {'ENABLED' if use_ai else 'DISABLED'}.")
            
            decision_to_attack = False
            if use_ai:
                self.logger.info("4️⃣ Checking enemy loot with AI...")
                decision_to_attack = self._check_loot_with_ai(screenshot_path)
            else:
                self.logger.info("4️⃣ Performing simple loot check (AI Disabled)...")
                decision_to_attack = self._check_loot()
            
            if decision_to_attack:
                self.logger.info("✅ Base is good! Proceeding with attack!")
                return True
            
            self.logger.info("❌ Base not suitable. Moving to next base...")
        
        self.logger.warning(f"Could not find good loot after {max_attempts} attempts")
        return False
    
    def _check_loot_with_ai(self, screenshot_path: str) -> bool:
        """Analyze the base with Gemini and decide whether to attack."""
        min_gold = self.config.get('ai_analyzer.min_gold', 300000)
        min_elixir = self.config.get('ai_analyzer.min_elixir', 300000)
        min_dark = self.config.get('ai_analyzer.min_dark_elixir', 5000)
        max_th_level = self.config.get('auto_attacker.max_th_level', 16)

        analysis = self.ai_analyzer.analyze_base(screenshot_path, min_gold, min_elixir, min_dark,
                                                  max_th_level=max_th_level)

        if analysis.get("error"):
            self.logger.error(f"AI analysis failed: {analysis['reasoning']}")
            return False

        # Log detailed loot comparison for debugging
        loot = analysis.get("loot", {})
        extracted_gold = loot.get("gold", 0)
        extracted_elixir = loot.get("elixir", 0)
        extracted_dark = loot.get("dark_elixir", 0)
        townhall_level = analysis.get("townhall_level", 0)
        
        self.logger.info(f"🔍 AI Extracted Loot: Gold={extracted_gold:,}, Elixir={extracted_elixir:,}, Dark={extracted_dark:,}")
        self.logger.info(f"🏰 Town Hall Level: {townhall_level}")
        self.logger.info(f"📋 Requirements: Gold={min_gold:,}, Elixir={min_elixir:,}, Dark={min_dark:,}, Max TH={max_th_level}")
        
        # Check loot requirements
        gold_ok = extracted_gold >= min_gold
        elixir_ok = extracted_elixir >= min_elixir
        dark_ok = extracted_dark >= min_dark
        th_ok = townhall_level <= max_th_level
        
        self.logger.info(f"✅/❌ Meets Requirements: Gold={gold_ok}, Elixir={elixir_ok}, Dark={dark_ok}, TH_Level={th_ok}")
        
        # Override AI decision if Town Hall is too high
        if townhall_level > max_th_level:
            self.logger.info(f"❌ Overriding AI: Town Hall {townhall_level} is too strong (max allowed: {max_th_level})")
            return False

        recommendation = analysis.get("recommendation", "SKIP").upper()
        attack = recommendation == "ATTACK"

        # Store analysis for loot tracking in the attack loop
        if attack:
            self._last_ai_analysis = analysis

        return attack

    def _check_loot(self) -> bool:
        """Check if enemy base has good loot.

        Simple OCR-based loot reading is not yet implemented.  This method
        logs a warning and returns ``False`` so that the bot skips the base
        rather than blindly attacking every one it encounters.  Enable AI
        analysis (``ai_analyzer.enabled = true`` in config) for automatic
        loot detection.
        """
        self.logger.warning(
            "⚠️ Simple loot check: OCR is not implemented. "
            "Returning False (SKIP) to avoid attacking every base. "
            "Enable AI analysis via 'ai_analyzer.enabled' in config.json for "
            "automatic loot detection."
        )
        return False
    
    def _click_end_button_and_retry(self) -> None:
        """Click end button to abort the current search, then confirm the surrender dialog."""
        coords = self._get_coords()
        delay_variance = self.config.get('anti_ban.delay_variance', 0.3)
        click_offset = self.config.get('anti_ban.click_offset_range', 5)

        if 'end_button' in coords:
            end_coord = coords['end_button']
            self.logger.info(f"🔄 Clicking end_button at ({end_coord['x']}, {end_coord['y']})")
            hx, hy = humanize_click(end_coord['x'], end_coord['y'], click_offset)
            pyautogui.click(hx, hy)
            time.sleep(humanize_delay(2.0, delay_variance))

            # After clicking end_button a surrender/confirm dialog appears.
            # First click the surrender button (if mapped), then confirm.
            if 'surrender_button' in coords:
                surr_coord = coords['surrender_button']
                self.logger.info(f"🔄 Clicking surrender_button at ({surr_coord['x']}, {surr_coord['y']})")
                hx, hy = humanize_click(surr_coord['x'], surr_coord['y'], click_offset)
                pyautogui.click(hx, hy)
                time.sleep(humanize_delay(1.5, delay_variance))

            if 'surrender_confirm' in coords:
                conf_coord = coords['surrender_confirm']
                self.logger.info(f"🔄 Clicking surrender_confirm at ({conf_coord['x']}, {conf_coord['y']})")
                hx, hy = humanize_click(conf_coord['x'], conf_coord['y'], click_offset)
                pyautogui.click(hx, hy)
                time.sleep(humanize_delay(2.0, delay_variance))
        else:
            self.logger.warning("end_button not mapped - cannot retry automatically")
    
    def _is_on_home_base(self) -> Optional[bool]:
        """Check whether the bot is already on the home base screen.

        Uses the ``return_home`` template to determine screen state:
        * ``True``  – template not visible → already on home base.
        * ``False`` – template visible     → still need to click Return Home.
        * ``None``  – template file absent → cannot determine screen state.
        """
        if not os.path.exists(_RETURN_HOME_TEMPLATE):
            return None
        match = self.screen_capture.find_template_on_screen(
            _RETURN_HOME_TEMPLATE, threshold=0.8
        )
        return match is None

    def _return_home(self) -> None:
        """Return to home base after battle, with up to 3 click attempts.

        Before clicking, the method checks whether the return_home template
        button is still visible on screen.  If it is not visible, the bot is
        already on the home base and no click is needed — this avoids wasting
        ~20 seconds clicking a position where no button exists.
        """
        coords = self._get_coords()
        delay_variance = self.config.get('anti_ban.delay_variance', 0.3)
        click_offset = self.config.get('anti_ban.click_offset_range', 5)

        self.logger.info("🏠 Returning to home base...")

        # If the return_home template is available, use it to check whether
        # we are already on the home screen (button not visible → already home).
        already_home = self._is_on_home_base()
        if already_home is True:
            self.logger.info("✅ Already on home base (return_home button not visible)")
            return

        if 'return_home' not in coords:
            self.logger.warning("return_home button not mapped")
            return

        home_coord = coords['return_home']
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            self.logger.info(
                f"Clicking return_home at ({home_coord['x']}, {home_coord['y']}) "
                f"(attempt {attempt}/{max_attempts})"
            )
            hx, hy = humanize_click(home_coord['x'], home_coord['y'], click_offset)
            pyautogui.click(hx, hy)
            time.sleep(humanize_delay(5.0, delay_variance))

            # After clicking, check if the button has disappeared (home reached).
            if self._is_on_home_base() is True:
                self.logger.info("✅ Returned to home base")
                return

            # Give the game a moment to respond; if we're on the last attempt
            # we treat the click as successful regardless.
            if attempt < max_attempts:
                # A short extra wait between retries to let the UI settle.
                time.sleep(humanize_delay(2.0, delay_variance))

        self.logger.info("✅ Returned to home base")
    
    def _get_next_attack_session(self) -> str:
        """Get the next attack session from rotation"""
        if not self.attack_sessions:
            return ""
        
        session = self.attack_sessions[self.current_session_index]
        self.current_session_index = (self.current_session_index + 1) % len(self.attack_sessions)
        return session

    def _select_best_strategy(self, screenshot_path: Optional[str]) -> str:
        """Select the best attack strategy for the current base.

        Uses AI strategy selection when enabled and multiple strategies are
        available; otherwise falls back to round-robin rotation.

        Args:
            screenshot_path: Path to a screenshot of the enemy base (may be
                ``None`` or empty if no screenshot was captured).

        Returns:
            The session name to use for the attack.
        """
        strategy_ai_enabled = self.config.get('strategy_selection.enabled', True) and \
                               self.config.get('strategy_selection.use_ai', True)
        strategy_metadata = self.config.get('strategy_selection.strategies', {})

        # Build list of strategies enriched with metadata
        strategies = []
        for session_name in self.attack_sessions:
            meta = strategy_metadata.get(session_name, {})
            strategies.append({
                'session_name': session_name,
                'name': meta.get('name', session_name),
                'description': meta.get('description', ''),
            })

        # Skip AI call if disabled, only one strategy, or no screenshot available
        if (not strategy_ai_enabled
                or len(strategies) <= 1
                or not screenshot_path
                or not self.config.get('ai_analyzer.enabled', False)):
            return self._get_next_attack_session()

        self.logger.info("🧠 Using AI to select best attack strategy...")
        result = self.ai_analyzer.select_strategy(screenshot_path, strategies)

        if result.get('error'):
            self.logger.warning(f"⚠️ AI strategy selection failed, using rotation. Reason: {result.get('reasoning')}")
            return self._get_next_attack_session()

        selected = result.get('selected_strategy', '')
        if selected in self.attack_sessions:
            self.logger.info(f"🎯 AI selected strategy: {selected} — {result.get('reasoning', '')}")
            return selected

        self.logger.warning(f"⚠️ AI returned unknown strategy '{selected}', using rotation.")
        return self._get_next_attack_session()

    # ── Dashboard & logging ───────────────────────────────────────────────────

    def _print_dashboard(self) -> None:
        """Print a compact live dashboard after each attack cycle."""
        with self._stats_lock:
            snap = self.stats.copy()

        now = datetime.now()
        if snap['start_time']:
            elapsed = now - snap['start_time']
            total_secs = int(elapsed.total_seconds())
            runtime_str = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
            runtime_hours = elapsed.total_seconds() / 3600
        else:
            runtime_str = "0h 0m"
            runtime_hours = 0

        total = snap['total_attacks']
        success = snap['successful_attacks']
        success_pct = (success / max(total, 1)) * 100
        atk_per_hr = total / max(runtime_hours, 1)

        max_attacks_per_session = self.config.get('anti_ban.max_attacks_per_session', 100)
        break_every_n = self.config.get('anti_ban.break_every_n_attacks', 10)
        next_break = break_every_n - (total % break_every_n) if break_every_n > 0 else 0

        total_gold = snap['total_gold_farmed']
        total_elixir = snap['total_elixir_farmed']
        total_dark = snap['total_dark_farmed']
        best_loot = snap['best_attack_loot']
        best_num = snap['best_attack_number']
        avg_gold = total_gold // max(success, 1)
        avg_elixir = total_elixir // max(success, 1)
        avg_dark = total_dark // max(success, 1)

        last_atk = snap['last_attack_time'].strftime("%H:%M:%S") if snap['last_attack_time'] else "N/A"
        # current_session_index already advanced past the last used session; step back safely
        if self.attack_sessions:
            last_idx = (self.current_session_index - 1) % len(self.attack_sessions)
            session_name = self.attack_sessions[last_idx]
        else:
            session_name = "N/A"

        width = 50
        border = "╔" + "═" * (width - 2) + "╗"
        mid    = "╠" + "═" * (width - 2) + "╣"
        bottom = "╚" + "═" * (width - 2) + "╝"

        def row(text: str) -> str:
            pad = width - 4 - len(text)
            return f"║ {text}{' ' * max(pad, 0)} ║"

        lines = [
            border,
            row("        COC ATTACK BOT - DASHBOARD"),
            mid,
            row(f"Runtime: {runtime_str:<10} │ Status: {'ATTACKING' if self.is_running else 'STOPPED'}"),
            row(f"Attacks: {total}/{max_attacks_per_session:<6}  │ Success: {success_pct:.0f}%"),
            row(f"Atk/hr:  {atk_per_hr:<10.1f} │ Next break: {next_break} more"),
            mid,
            row("RESOURCES FARMED"),
            row(f"💰 Gold:   {total_gold:>12,}  │ Avg: {avg_gold:,}/atk"),
            row(f"💧 Elixir: {total_elixir:>12,}  │ Avg: {avg_elixir:,}/atk"),
            row(f"⚫ Dark:   {total_dark:>12,}  │ Avg: {avg_dark:,}/atk"),
            row(f"🏆 Best:   {best_loot:,} (Attack #{best_num})"),
            mid,
            row(f"Last Atk: {last_atk:<12} │ Session: {session_name}"),
            bottom,
        ]
        print("\n".join(lines))

    def _print_session_summary(self) -> None:
        """Print a final summary when the session ends."""
        with self._stats_lock:
            snap = self.stats.copy()

        now = datetime.now()
        if snap['start_time']:
            elapsed = now - snap['start_time']
            total_secs = int(elapsed.total_seconds())
            runtime_str = (
                f"{total_secs // 3600}h "
                f"{(total_secs % 3600) // 60}m "
                f"{total_secs % 60}s"
            )
            runtime_hours = elapsed.total_seconds() / 3600
        else:
            runtime_str = "0h 0m 0s"
            runtime_hours = 0

        total = snap['total_attacks']
        success = snap['successful_attacks']
        failed = snap['failed_attacks']
        success_pct = (success / max(total, 1)) * 100
        atk_per_hr = total / max(runtime_hours, 1)

        total_gold = snap['total_gold_farmed']
        total_elixir = snap['total_elixir_farmed']
        total_dark = snap['total_dark_farmed']
        best_loot = snap['best_attack_loot']
        best_num = snap['best_attack_number']
        avg_gold = total_gold // max(success, 1)
        avg_elixir = total_elixir // max(success, 1)
        avg_dark = total_dark // max(success, 1)

        sep = "═" * 43
        print(f"\n{sep}")
        print("       SESSION COMPLETE SUMMARY")
        print(sep)
        print(f"Runtime:           {runtime_str}")
        print(f"Total Attacks:     {total}")
        print(f"Successful:        {success} ({success_pct:.0f}%)")
        print(f"Failed:            {failed}")
        print()
        print("TOTAL LOOT FARMED:")
        print(f"  Gold:            {total_gold:,}")
        print(f"  Elixir:          {total_elixir:,}")
        print(f"  Dark Elixir:     {total_dark:,}")
        print()
        print(f"Best Attack:       {best_loot:,} gold+elixir (Attack #{best_num})")
        print(f"Average Loot/atk:  {avg_gold:,} gold  /  {avg_elixir:,} elixir  /  {avg_dark:,} dark")
        print(f"Attacks/hour:      {atk_per_hr:.1f}")
        print(sep)

    def _save_session_stats(self) -> None:
        """Save session statistics to a daily JSON log file."""
        save_stats = self.config.get('dashboard.save_session_stats', True)
        if not save_stats:
            return

        stats_dir = self.config.get('dashboard.stats_directory', 'logs')
        try:
            os.makedirs(stats_dir, exist_ok=True)
        except OSError as e:
            self.logger.warning(f"Could not create stats directory '{stats_dir}': {e}")
            return

        with self._stats_lock:
            snap = self.stats.copy()

        now = datetime.now()
        filename = os.path.join(stats_dir, f"stats_{now.strftime('%Y-%m-%d')}.json")

        # Serialise datetimes to strings
        def _serialize(v):
            return v.isoformat() if isinstance(v, datetime) else v

        total = snap['total_attacks']
        success = snap['successful_attacks']
        runtime_hours = 0.0
        if snap['start_time']:
            runtime_hours = (now - snap['start_time']).total_seconds() / 3600

        record = {
            'session_end': now.isoformat(),
            'session_start': _serialize(snap['start_time']),
            'runtime_hours': round(runtime_hours, 3),
            'total_attacks': total,
            'successful_attacks': success,
            'failed_attacks': snap['failed_attacks'],
            'success_rate_pct': round((success / max(total, 1)) * 100, 1),
            'attacks_per_hour': round(total / max(runtime_hours, 1), 2),
            'total_gold_farmed': snap['total_gold_farmed'],
            'total_elixir_farmed': snap['total_elixir_farmed'],
            'total_dark_farmed': snap['total_dark_farmed'],
            'best_attack_loot': snap['best_attack_loot'],
            'best_attack_number': snap['best_attack_number'],
            'configured_sessions': list(self.attack_sessions),
        }

        # Append to existing daily file if present
        existing = []
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as fh:
                    existing = json.load(fh)
                    if not isinstance(existing, list):
                        existing = [existing]
            except (json.JSONDecodeError, OSError):
                existing = []

        existing.append(record)
        try:
            with open(filename, 'w', encoding='utf-8') as fh:
                json.dump(existing, fh, indent=2)
            self.logger.info(f"📊 Session stats saved to {filename}")
        except OSError as e:
            self.logger.warning(f"Could not save session stats: {e}")
    
    def get_stats(self) -> Dict:
        """Get automation statistics"""
        with self._stats_lock:
            stats_snapshot = self.stats.copy()

        if stats_snapshot['start_time']:
            runtime = datetime.now() - stats_snapshot['start_time']
            runtime_hours = runtime.total_seconds() / 3600
        else:
            runtime_hours = 0
        
        return {
            'is_running': self.is_running,
            'total_attacks': stats_snapshot['total_attacks'],
            'successful_attacks': stats_snapshot['successful_attacks'],
            'failed_attacks': stats_snapshot['failed_attacks'],
            'success_rate': (stats_snapshot['successful_attacks'] / max(stats_snapshot['total_attacks'], 1)) * 100,
            'runtime_hours': runtime_hours,
            'attacks_per_hour': stats_snapshot['total_attacks'] / max(runtime_hours, 1),
            'last_attack': stats_snapshot['last_attack_time'].strftime("%H:%M:%S") if stats_snapshot['last_attack_time'] else "None",
            'configured_sessions': self.attack_sessions.copy(),
            'total_loot': {
                'gold': stats_snapshot['total_gold_farmed'],
                'elixir': stats_snapshot['total_elixir_farmed'],
                'dark_elixir': stats_snapshot['total_dark_farmed'],
            },
        }
    
    def update_loot_requirements(self, min_gold: int = None, min_elixir: int = None, min_dark_elixir: int = None):
        """Update minimum loot requirements"""
        if min_gold is not None:
            self.config.set('ai_analyzer.min_gold', min_gold)
        if min_elixir is not None:
            self.config.set('ai_analyzer.min_elixir', min_elixir)
        if min_dark_elixir is not None:
            self.config.set('ai_analyzer.min_dark_elixir', min_dark_elixir)
        
        self.logger.info(f"Updated loot requirements: Gold={self.config.get('ai_analyzer.min_gold')}, Elixir={self.config.get('ai_analyzer.min_elixir')}, Dark={self.config.get('ai_analyzer.min_dark_elixir')}")
    
    def configure_buttons(self) -> Dict[str, str]:
        """Get list of required button mappings for the simplified automation"""
        return {
            'attack': 'Main attack button on home screen',
            'find_a_match': 'Find match/search button in attack screen',
            'attack_confirm_button': 'Green attack confirm button after find_a_match (new CoC update)',
            'next_button': 'Next button to skip bases with low loot',
            'end_button': 'End/surrender button to abort a running search or battle',
            'surrender_button': 'Surrender confirmation button shown after end_button',
            'surrender_confirm': 'Final "Okay/Yes" button in the surrender confirmation dialog',
            'return_home': 'Return home button after battle completion',
            'enemy_gold': 'Enemy gold display for loot checking',
            'enemy_elixir': 'Enemy elixir display for loot checking',
            'enemy_dark_elixir': 'Enemy dark elixir display for loot checking'
        }