"""
Auto Attacker - Automated continuous attack system for COC
"""

import os
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

# Template images used for battle-end detection.
# Place either or both in the `templates/` directory for early battle-end detection.
_BATTLE_END_TEMPLATE = os.path.join("templates", "battle_end.png")
_RETURN_HOME_TEMPLATE = os.path.join("templates", "return_home.png")

# Pixel-colour change threshold used by the return_home heuristic detector.
# A cumulative RGB-channel delta above this value is considered a significant
# colour change indicating that the "Return Home" button has appeared.
_PIXEL_COLOR_DIFF_THRESHOLD = 30

# Minimum seconds elapsed before the pixel-colour heuristic will declare the
# battle finished.  This prevents false positives caused by brief colour
# changes that can occur at the very start of the battle.
_MIN_BATTLE_ELAPSED_SECS = 30


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
        self.stats = {
            'total_attacks': 0,
            'successful_attacks': 0,
            'failed_attacks': 0,
            'start_time': None,
            'last_attack_time': None
        }
        
        self.attack_sessions = self.config.get('auto_attacker.attack_sessions', [])
        self.max_search_attempts = self.config.get('auto_attacker.max_search_attempts', 10)
        self.current_session_index = 0
        
        # Cached coordinates (invalidated on each attack cycle)
        self._cached_coords = None
        
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
        if self.is_running:
            print("Auto attacker already running")
            return
        
        if not self.attack_sessions:
            self.logger.error("No attack sessions configured. Please add at least one session.")
            return
        
        self.is_running = True
        self.stats['start_time'] = datetime.now()
        
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
        
        self.logger.info("Auto attacker stopped")
    
    def _get_coords(self) -> Dict:
        """Return cached coordinates, refreshing once per attack cycle."""
        if self._cached_coords is None:
            self._cached_coords = self.coordinate_mapper.get_coordinates()
        return self._cached_coords

    def _auto_attack_loop(self) -> None:
        """Main automation loop"""
        try:
            while self.is_running:
                # Check emergency stop
                if keyboard.is_pressed('ctrl+alt+s'):
                    self.logger.warning("Emergency stop activated!")
                    break
                
                # Refresh coordinate cache at start of each cycle
                self._cached_coords = None
                
                self.logger.info("🎯 Starting new attack cycle...")
                
                # Execute attack sequence
                if self._execute_attack_sequence():
                    with self._stats_lock:
                        self.stats['successful_attacks'] += 1
                    self.logger.info("✅ Attack sequence completed successfully")
                else:
                    with self._stats_lock:
                        self.stats['failed_attacks'] += 1
                    self.logger.warning("❌ Attack sequence failed")
                
                with self._stats_lock:
                    self.stats['total_attacks'] += 1
                    self.stats['last_attack_time'] = datetime.now()
                
                # Short break between attacks
                if self.is_running:
                    delay = random.randint(5, 15)
                    self.logger.info(f"⏳ Waiting {delay} seconds before next attack...")
                    time.sleep(delay)
                    
        except Exception as e:
            self.logger.error(f"Auto attack loop error: {e}")
        finally:
            self.is_running = False
    
    def _execute_attack_sequence(self) -> bool:
        """Execute the complete attack sequence following your exact process"""
        try:
            coords = self._get_coords()
            
            # Step 1: Click attack button
            if 'attack' not in coords:
                self.logger.error("Attack button not mapped")
                return False
                
            attack_coord = coords['attack']
            self.logger.info(f"1️⃣ Clicking attack button at ({attack_coord['x']}, {attack_coord['y']})")
            pyautogui.click(attack_coord['x'], attack_coord['y'])
            time.sleep(2)  # Wait for attack screen
            
            # Step 2-6: Find good loot target
            if not self._find_good_loot_target():
                self.logger.warning("Could not find good loot target")
                return False
            
            # Step 7: Start attack recording (only after good loot found)
            session_name = self._get_next_attack_session()
            self.logger.info(f"🎯 Starting attack with session: {session_name}")
            
            if not self.attack_player.play_attack(session_name, speed=1.0, auto_mode=True):
                self.logger.error("Failed to start attack recording")
                return False
            
            self.logger.info("✅ Attack recording started - troops deploying...")
            
            # Step 8: Wait for battle completion (detect end instead of fixed 3 min)
            self._wait_for_battle_end()
            
            # Step 9: Return home
            self._return_home()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Attack sequence failed: {e}")
            return False
    
    def _wait_for_battle_end(self) -> None:
        """Wait for battle to end by checking for battle-end indicators.

        Detection priority:
        1. ``templates/battle_end.png`` – template match on screen.
        2. ``templates/return_home.png`` – template match on screen.
        3. ``return_home`` coordinate – pixel-colour change heuristic.
        4. Fixed timeout (configurable via ``auto_attacker.battle_timeout``).

        The method also waits for the playback thread to finish first so that
        troop deployment is complete before we start polling (fixes race
        condition between playback and battle-end detection).
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
            initial_color = self.screen_capture.get_pixel_color(
                home_coord['x'], home_coord['y']
            )
            elapsed = 0
            while elapsed < battle_timeout and self.is_running:
                current_color = self.screen_capture.get_pixel_color(
                    home_coord['x'], home_coord['y']
                )
                color_diff = sum(
                    abs(current_color[i] - initial_color[i]) for i in range(3)
                )
                # Require a significant colour change AND at least the minimum
                # elapsed time to avoid false positives at battle start.
                if color_diff > _PIXEL_COLOR_DIFF_THRESHOLD and elapsed >= _MIN_BATTLE_ELAPSED_SECS:
                    self.logger.info(
                        f"🏁 Battle ended after ~{elapsed}s "
                        f"(pixel colour change at return_home detected)"
                    )
                    return
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
        
        if 'attack_confirm_button' not in coords:
            self.logger.error("attack_confirm_button not mapped - this button is required since the latest CoC update")
            return False
        
        confirm_coord = coords['attack_confirm_button']
        self.logger.info(f"⚔️ Clicking attack_confirm_button at ({confirm_coord['x']}, {confirm_coord['y']})")
        pyautogui.click(confirm_coord['x'], confirm_coord['y'])
        time.sleep(3)  # Wait for matchmaking to find a base
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
                pyautogui.click(find_coord['x'], find_coord['y'])
                time.sleep(2)  # Wait for confirm button to appear
                
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
                pyautogui.click(next_coord['x'], next_coord['y'])
                time.sleep(3)
            
            # Wait for base to load
            self.logger.info("3️⃣ Waiting for base to load...")
            time.sleep(5)
            
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

        analysis = self.ai_analyzer.analyze_base(screenshot_path, min_gold, min_elixir, min_dark)

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
        max_th_level = self.config.get('auto_attacker.max_th_level', 12)
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
        return recommendation == "ATTACK"

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
        """Click end button when Town Hall is not detected and retry"""
        coords = self._get_coords()
        
        if 'end_button' in coords:
            end_coord = coords['end_button']
            self.logger.info(f"🔄 Clicking end_button at ({end_coord['x']}, {end_coord['y']})")
            pyautogui.click(end_coord['x'], end_coord['y'])
            time.sleep(3)  # Wait for end action to complete
        else:
            self.logger.warning("end_button not mapped - cannot retry automatically")
    
    def _return_home(self) -> None:
        """Return to home base after battle"""
        coords = self._get_coords()
        
        self.logger.info("🏠 Returning to home base...")
        
        # Only click return_home button
        if 'return_home' in coords:
            home_coord = coords['return_home']
            self.logger.info(f"Clicking return_home at ({home_coord['x']}, {home_coord['y']})")
            pyautogui.click(home_coord['x'], home_coord['y'])
            time.sleep(5)  # Wait to return home
        else:
            self.logger.warning("return_home button not mapped")
        
        self.logger.info("✅ Returned to home base")
    
    def _get_next_attack_session(self) -> str:
        """Get the next attack session from rotation"""
        if not self.attack_sessions:
            return ""
        
        session = self.attack_sessions[self.current_session_index]
        self.current_session_index = (self.current_session_index + 1) % len(self.attack_sessions)
        return session
    
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
            'configured_sessions': self.attack_sessions.copy()
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
            'return_home': 'Return home button after battle completion',
            'enemy_gold': 'Enemy gold display for loot checking',
            'enemy_elixir': 'Enemy elixir display for loot checking',
            'enemy_dark_elixir': 'Enemy dark elixir display for loot checking'
        }