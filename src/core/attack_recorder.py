"""
Attack Recorder - Records user attack sessions for later playback
"""

import json
import os
import time
import pyautogui
import keyboard
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    import win32api
    _HAS_WIN32API = True
except ImportError:
    _HAS_WIN32API = False

try:
    from PIL import Image  # noqa: F401 – used indirectly via pyautogui.screenshot()
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

class AttackRecorder:
    """Records attack sessions including mouse movements, clicks, and timing"""
    
    def __init__(self, auto_detect_clicks: bool = True, troop_bar_config: Optional[Dict] = None,
                 logger=None):
        self.recordings_dir = "recordings"
        self.current_recording = []
        self.recording_thread = None
        self.is_recording = False
        self.start_time = None
        self.session_name = None
        self.auto_detect_clicks = auto_detect_clicks
        self._last_click_time = 0
        self._config_warned = False
        self._fallback_warned = False
        self._logger = logger
        
        # Troop bar configuration (will be resolved when recording starts)
        self._troop_bar_config = troop_bar_config or {}
        
        # Create recordings directory
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        self._log("Attack Recorder initialized")
        self._log("Recording Controls:")
        self._log("  F5 - Start/Stop recording")
        self._log("  F6 - Manual click recording (backup method)")
        self._log("  F7 - Add delay marker")
        self._log("  ESC - Cancel recording")
        if self.auto_detect_clicks:
            self._log("✅ Auto-click detection is ENABLED - clicks will be recorded automatically")
        else:
            self._log("⚠️ Auto-click detection is DISABLED (use F6 for manual recording)", "warning")

    def _log(self, msg: str, level: str = "info") -> None:
        """Log via Logger if available, otherwise print."""
        if self._logger:
            getattr(self._logger, level)(msg)
        else:
            print(msg)
    
    def start_recording(self, session_name: str) -> None:
        """Start recording an attack session"""
        if self.is_recording:
            self._log("Already recording a session")
            return
        
        self.session_name = session_name
        self.current_recording = []
        self.is_recording = True
        self.start_time = time.time()
        
        self._log(f"\n=== RECORDING ATTACK SESSION: {session_name} ===")
        self._log("Instructions:")
        if self.auto_detect_clicks:
            self._log("1. Perform your attack as normal")
            self._log("2. All clicks will be recorded automatically")
            self._log("3. Press F7 to add delays between actions")
            self._log("4. Press F5 to stop recording")
            self._log("5. Press ESC to cancel")
            self._log("\nRECORDING STARTED - Auto-detection enabled...")
        else:
            self._log("1. Navigate to your attack position")
            self._log("2. Press F6 to record each click manually")
            self._log("3. Press F7 to add delays between actions")
            self._log("4. Press F5 to stop recording")
            self._log("5. Press ESC to cancel")
            self._log("\nRECORDING STARTED - Use F6 to record clicks...")
            self._log("(Auto-click detection is disabled)")
        
        # Start the recording thread
        self.recording_thread = threading.Thread(target=self._recording_loop)
        self.recording_thread.daemon = True
        self.recording_thread.start()
    
    def stop_recording(self) -> Optional[str]:
        """Stop the current recording and save it"""
        if not self.is_recording:
            self._log("No recording session active")
            return None
        
        self.is_recording = False
        
        if self.recording_thread:
            self.recording_thread.join(timeout=1)
        
        if self.current_recording:
            filepath = self._save_recording(self.session_name, self.current_recording)
            self._log(f"\nRecording saved: {filepath}")
            self._log(f"Total actions recorded: {len(self.current_recording)}")
            return filepath
        else:
            self._log("No actions recorded")
            return None
    
    def _recording_loop(self) -> None:
        """Main recording loop that captures user input"""
        last_mouse_pos = pyautogui.position()
        
        try:
            while self.is_recording:
                current_time = time.time() - self.start_time
                
                # Check for manual recording hotkeys
                if keyboard.is_pressed('esc'):
                    self._log("\nRecording cancelled")
                    self.is_recording = False
                    break
                
                if keyboard.is_pressed('f5'):
                    self._log("\nStopping recording")
                    self.is_recording = False
                    break
                
                if keyboard.is_pressed('f6'):
                    # Manual click recording (backup method)
                    x, y = pyautogui.position()
                    self._record_click(x, y, current_time)
                    
                    # Wait for key release to prevent spam
                    while keyboard.is_pressed('f6'):
                        time.sleep(0.1)
                
                if keyboard.is_pressed('f7'):
                    # Add delay marker using a fixed default to avoid blocking the thread
                    delay = 1.0
                    self._add_action('delay', 0, 0, current_time, {'duration': delay})
                    self._log(f"Added {delay}s delay")
                    
                    # Wait for key release
                    while keyboard.is_pressed('f7'):
                        time.sleep(0.1)
                
                # Auto-click detection (enabled by default)
                if self.auto_detect_clicks:
                    if _HAS_WIN32API:
                        # Method 1: Use win32 API for reliable mouse detection
                        left_button_state = win32api.GetKeyState(0x01)  # VK_LBUTTON
                        right_button_state = win32api.GetKeyState(0x02)  # VK_RBUTTON
                        
                        if left_button_state < 0 or right_button_state < 0:  # Button is pressed
                            x, y = pyautogui.position()
                            # Check if this is a new click (avoid duplicates)
                            if (current_time - self._last_click_time) > 0.15:  # 150ms debounce
                                self._record_click(x, y, current_time)
                                self._last_click_time = current_time
                    else:
                        # Method 2: Fallback using pyautogui mouse detection
                        try:
                            if hasattr(pyautogui, '_mouseDown') and pyautogui._mouseDown:
                                x, y = pyautogui.position()
                                if (current_time - self._last_click_time) > 0.15:
                                    self._record_click(x, y, current_time)
                                    self._last_click_time = current_time
                        except (AttributeError, TypeError):
                            if not self._fallback_warned:
                                self._log("⚠️ Auto-click detection failed - use F6 to manually record clicks", "warning")
                                self._fallback_warned = True
                
                # Track significant mouse movements
                current_mouse_pos = pyautogui.position()
                if self._distance(last_mouse_pos, current_mouse_pos) > 50:
                    mx, my = current_mouse_pos
                    screen_width, screen_height = pyautogui.size()
                    if mx >= 0 and my >= 0 and mx < screen_width and my < screen_height:
                        self._add_action('move', mx, my, current_time)
                    last_mouse_pos = current_mouse_pos
                
                time.sleep(0.1)  # 10 FPS polling — well within 150ms click debounce window
        
        except Exception as e:
            self._log(f"Recording error: {e}", "error")
            self.is_recording = False
    
    def set_troop_bar_config(self, cfg: Dict) -> None:
        """Update the troop bar configuration and reset the one-shot warning flag."""
        self._troop_bar_config = cfg
        self._config_warned = False
    def toggle_auto_click_detection(self) -> bool:
        """Toggle auto-click detection on/off"""
        self.auto_detect_clicks = not self.auto_detect_clicks
        status = "ENABLED" if self.auto_detect_clicks else "DISABLED"
        self._log(f"Auto-click detection: {status}")
        return self.auto_detect_clicks
    
    def _get_troop_bar_bounds(self) -> Dict:
        """Get troop bar region bounds, resolved against current screen size."""
        screen_width, screen_height = pyautogui.size()
        cfg = self._troop_bar_config

        if cfg.get('calibrated', False):
            # Use values saved by the calibration wizard
            y_min_offset = cfg.get('y_min_offset', max(100, int(screen_height * 0.08)))
            num_slots = cfg.get('num_slots', 8)
            slot_width = cfg.get('slot_width', 70)
            x_start = cfg.get('x_start', 0)
            return {
                'y_min': screen_height - y_min_offset,
                'y_max': screen_height,
                'x_start': x_start,
                'x_end': x_start + num_slots * slot_width,
                'slot_width': slot_width,
                'num_slots': num_slots,
            }

        # Smart defaults based on screen resolution when not yet calibrated.
        # The CoC troop bar is roughly in the bottom ~8 % of the screen and
        # spans about 45 % of the screen width centred horizontally.
        y_min_offset = cfg.get('y_min_offset', max(100, int(screen_height * 0.08)))
        num_slots = cfg.get('num_slots', 8)
        estimated_bar_width = max(1, int(screen_width * 0.45))
        slot_width = cfg.get('slot_width', estimated_bar_width // max(num_slots, 1))
        # Only use the stored x_start when it is non-zero (i.e. deliberately set);
        # otherwise centre the estimated bar on the screen.
        stored_x_start = cfg.get('x_start', 0)
        x_start = stored_x_start if stored_x_start != 0 else (screen_width - estimated_bar_width) // 2
        return {
            'y_min': screen_height - y_min_offset,
            'y_max': screen_height,
            'x_start': x_start,
            'x_end': x_start + num_slots * slot_width,
            'slot_width': slot_width,
            'num_slots': num_slots,
        }

    def _validate_troop_bar_config(self) -> None:
        """Warn once if the troop bar config looks wrong for the current screen resolution."""
        if self._config_warned:
            return
        self._config_warned = True
        bounds = self._get_troop_bar_bounds()
        screen_width, _ = pyautogui.size()
        total_bar_width = bounds['num_slots'] * bounds['slot_width']
        if total_bar_width < screen_width * 0.1:
            self._log("⚠️ WARNING: Troop bar config seems too narrow for your screen resolution!", "warning")
            self._log(f"   Screen width: {screen_width}px, Troop bar width: {total_bar_width}px", "warning")
            self._log("   Run 'Calibrate Troop Bar' from the Auto Attack menu to fix this.", "warning")
        if bounds['x_start'] == 0 and screen_width > 1920:
            self._log("⚠️ WARNING: Troop bar x_start is 0 — this is likely wrong for your resolution!", "warning")
            self._log("   Run 'Calibrate Troop Bar' from the Auto Attack menu to fix this.", "warning")

    def _get_slot_index(self, x: int, bounds: Dict) -> int:
        """Return 0-based slot index for an x coordinate within the troop bar."""
        slot_width = bounds['slot_width']
        x_start = bounds['x_start']
        num_slots = bounds.get('num_slots', 8)
        if slot_width <= 0:
            return 0
        raw_index = (x - x_start) // slot_width
        return max(0, min(raw_index, num_slots - 1))

    def _capture_troop_icon(self, x: int, y: int, slot_index: int, bounds: Dict) -> Optional[str]:
        """
        Capture a small crop of the troop icon at the given slot and save it.
        Returns the saved file path, or None on failure.
        """
        if not _HAS_PIL:
            return None
        try:
            slot_width = bounds['slot_width']
            x_start = bounds['x_start'] + slot_index * slot_width
            icon_height = bounds['y_max'] - bounds['y_min']
            # Capture the slot region
            screenshot = pyautogui.screenshot(region=(x_start, bounds['y_min'], slot_width, icon_height))
            icons_dir = os.path.join(self.recordings_dir, 'icons')
            os.makedirs(icons_dir, exist_ok=True)
            icon_path = os.path.join(icons_dir, f"{self.session_name}_slot_{slot_index}.png")
            screenshot.save(icon_path)
            return icon_path
        except Exception as e:
            self._log(f"⚠️ Could not capture troop icon for slot {slot_index}: {e}", "warning")
            return None

    def _record_click(self, x: int, y: int, timestamp: float) -> None:
        """
        Record a click, detecting whether it falls in the troop bar.
        Troop bar clicks are saved as 'troop_select' actions with slot metadata
        and a captured icon image.  All other clicks are saved as plain 'click'.
        Clicks with negative or out-of-bounds coordinates are silently dropped.
        """
        screen_width, screen_height = pyautogui.size()
        if x < 0 or y < 0 or x >= screen_width or y >= screen_height:
            self._log(f"⚠️ Skipping click at ({x}, {y}) — out of screen bounds", "warning")
            return
        self._validate_troop_bar_config()
        bounds = self._get_troop_bar_bounds()
        in_troop_bar = (bounds['y_min'] <= y <= bounds['y_max'] and
                        bounds['x_start'] <= x <= bounds['x_end'])
        if in_troop_bar:
            slot_index = self._get_slot_index(x, bounds)
            icon_path = self._capture_troop_icon(x, y, slot_index, bounds)
            extra: Dict = {'slot_index': slot_index}
            if icon_path:
                extra['troop_icon'] = icon_path
            self._add_action('troop_select', x, y, timestamp, extra)
            self._log(f"🪖 Troop select recorded at ({x}, {y}) — slot {slot_index}")
        else:
            self._add_action('click', x, y, timestamp)
            self._log(f"🖱️ Click recorded at ({x}, {y})")

    def _add_action(self, action_type: str, x: int, y: int, timestamp: float, extra_data: Optional[Dict] = None) -> None:
        """Add an action to the current recording"""
        action = {
            'type': action_type,
            'x': x,
            'y': y,
            'timestamp': timestamp,
            'relative_time': timestamp
        }
        
        if extra_data:
            action.update(extra_data)
        
        self.current_recording.append(action)
    
    def _distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
        """Calculate distance between two points"""
        return ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5
    
    def _save_recording(self, name: str, recording: List[Dict]) -> str:
        """Save a recording to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.json"
        filepath = os.path.join(self.recordings_dir, filename)
        
        recording_data = {
            'name': name,
            'created': datetime.now().isoformat(),
            'duration': recording[-1]['timestamp'] if recording else 0,
            'actions': recording
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(recording_data, f, indent=2)
            return filepath
        except Exception as e:
            self._log(f"Error saving recording: {e}", "error")
            return ""
    
    def list_sessions(self) -> List[str]:
        """Get list of all recorded sessions"""
        if not os.path.exists(self.recordings_dir):
            return []
        
        sessions = []
        for file in os.listdir(self.recordings_dir):
            if file.endswith('.json'):
                sessions.append(file[:-5])  # Remove .json extension
        
        return sorted(sessions)
    
    def load_recording(self, session_name: str) -> Optional[Dict]:
        """Load a recording by name"""
        filepath = os.path.join(self.recordings_dir, f"{session_name}.json")
        
        if not os.path.exists(filepath):
            self._log(f"Recording not found: {session_name}", "error")
            return None
        
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            self._log(f"Error loading recording: {e}", "error")
            return None
    
    def delete_recording(self, session_name: str) -> bool:
        """Delete a recording"""
        filepath = os.path.join(self.recordings_dir, f"{session_name}.json")
        
        if not os.path.exists(filepath):
            self._log(f"Recording not found: {session_name}", "error")
            return False
        
        try:
            os.remove(filepath)
            self._log(f"Deleted recording: {session_name}")
            return True
        except Exception as e:
            self._log(f"Error deleting recording: {e}", "error")
            return False
    
    def get_recording_info(self, session_name: str) -> Optional[Dict]:
        """Get information about a recording"""
        recording = self.load_recording(session_name)
        if not recording:
            return None
        
        return {
            'name': recording.get('name', session_name),
            'created': recording.get('created', 'Unknown'),
            'duration': recording.get('duration', 0),
            'action_count': len(recording.get('actions', [])),
            'action_types': self._count_action_types(recording.get('actions', []))
        }
    
    def _count_action_types(self, actions: List[Dict]) -> Dict[str, int]:
        """Count the types of actions in a recording"""
        counts = {}
        for action in actions:
            action_type = action.get('type', 'unknown')
            counts[action_type] = counts.get(action_type, 0) + 1
        return counts 