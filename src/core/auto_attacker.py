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

# Path to battle-end template image (e.g. the "Return Home" button that appears when a battle ends)
_BATTLE_END_TEMPLATE = os.path.join("templates", "battle_end.png")


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
                    self.stats['successful_attacks'] += 1
                    self.logger.info("✅ Attack sequence completed successfully")
                else:
                    self.stats['failed_attacks'] += 1
                    self.logger.warning("❌ Attack sequence failed")
                
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
        """Wait for battle to end by checking for the battle-end indicator.
        
        If a battle_end template image exists, polls for it every 5 seconds
        so the bot can proceed as soon as the battle finishes instead of
        always waiting the full 3 minutes.  Falls back to a fixed 180 s
        wait when the template is not available.
        """
        battle_timeout = 180  # 3 minutes max
        poll_interval = 5     # seconds between checks

        has_template = os.path.exists(_BATTLE_END_TEMPLATE)

        if has_template:
            self.logger.info("⏳ Waiting for battle to end (polling for end indicator)...")
            elapsed = 0
            while elapsed < battle_timeout and self.is_running:
                # Check if battle-end indicator is visible on screen
                match = self.screen_capture.find_template_on_screen(
                    _BATTLE_END_TEMPLATE, threshold=0.8
                )
                if match:
                    self.logger.info(f"🏁 Battle ended after ~{elapsed}s (end indicator detected)")
                    return
                remaining = battle_timeout - elapsed
                self.logger.info(
                    f"⏳ Battle in progress... ~{remaining // 60}m {remaining % 60}s remaining"
                )
                time.sleep(poll_interval)
                elapsed += poll_interval
            self.logger.info("⏳ Battle timeout reached (180s)")
        else:
            self.logger.info(
                "⏳ Waiting 3 minutes for battle completion "
                f"(place a template at '{_BATTLE_END_TEMPLATE}' for early detection)..."
            )
            for remaining in range(battle_timeout, 0, -10):
                if not self.is_running:
                    break
                self.logger.info(
                    f"⏳ Battle in progress... {remaining // 60}m {remaining % 60}s remaining"
                )
                time.sleep(10)

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
            
            # Click find_a_match
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
            
            # Bad base, click next
            self.logger.info("❌ Base not suitable. Clicking next...")
            next_coord = coords['next_button']
            pyautogui.click(next_coord['x'], next_coord['y'])
            time.sleep(3)
        
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
        self.logger.info(f"📋 Requirements: Gold={min_gold:,}, Elixir={min_elixir:,}, Dark={min_dark:,}, Max TH=12")
        
        # Check loot requirements
        gold_ok = extracted_gold >= min_gold
        elixir_ok = extracted_elixir >= min_elixir
        dark_ok = extracted_dark >= min_dark
        th_ok = townhall_level <= 12
        
        self.logger.info(f"✅/❌ Meets Requirements: Gold={gold_ok}, Elixir={elixir_ok}, Dark={dark_ok}, TH_Level={th_ok}")
        
        # Override AI decision if Town Hall is too high
        if townhall_level > 12:
            self.logger.info(f"❌ Overriding AI: Town Hall {townhall_level} is too strong (max allowed: 12)")
            return False

        recommendation = analysis.get("recommendation", "SKIP").upper()
        return recommendation == "ATTACK"

    def _check_loot(self) -> bool:
        """Check if enemy base has good loot"""
        coords = self._get_coords()
        
        # Check each loot type
        loot_checks = {
            'gold': ('enemy_gold', self.config.get('ai_analyzer.min_gold', 300000)),
            'elixir': ('enemy_elixir', self.config.get('ai_analyzer.min_elixir', 300000)),
            'dark': ('enemy_dark_elixir', self.config.get('ai_analyzer.min_dark_elixir', 5000))
        }
        
        good_loot_count = 0
        
        for loot_name, (coord_name, min_value) in loot_checks.items():
            if coord_name in coords:
                coord = coords[coord_name]
                self.logger.info(f"Checking {loot_name} at ({coord['x']}, {coord['y']})")
                
                # Simple check - in real game you'd use OCR here
                # For now, assume good loot (you can implement OCR later)
                has_good_loot = True  # Placeholder
                
                if has_good_loot:
                    good_loot_count += 1
                    self.logger.info(f"✅ {loot_name.capitalize()}: Good")
                else:
                    self.logger.info(f"❌ {loot_name.capitalize()}: Too low")
        
        # Require at least 2 out of 3 loot types to be good
        is_good = good_loot_count >= 2
        
        if is_good:
            self.logger.info(f"✅ Loot check PASSED - {good_loot_count}/3 loot types are good")
        else:
            self.logger.info(f"❌ Loot check FAILED - Only {good_loot_count}/3 loot types are good")
        
        return is_good
    
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
        if self.stats['start_time']:
            runtime = datetime.now() - self.stats['start_time']
            runtime_hours = runtime.total_seconds() / 3600
        else:
            runtime_hours = 0
        
        return {
            'is_running': self.is_running,
            'total_attacks': self.stats['total_attacks'],
            'successful_attacks': self.stats['successful_attacks'],
            'failed_attacks': self.stats['failed_attacks'],
            'success_rate': (self.stats['successful_attacks'] / max(self.stats['total_attacks'], 1)) * 100,
            'runtime_hours': runtime_hours,
            'attacks_per_hour': self.stats['total_attacks'] / max(runtime_hours, 1),
            'last_attack': self.stats['last_attack_time'].strftime("%H:%M:%S") if self.stats['last_attack_time'] else "None",
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