"""
Attack Player - Plays back recorded attack sessions
"""

import json
import os
import time
import pyautogui
import keyboard
import threading
from typing import Dict, List, Optional
from .attack_recorder import AttackRecorder
from ..utils.humanizer import humanize_click, humanize_delay

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    from PIL import Image  # noqa: F401 – used indirectly via pyautogui.screenshot()
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

class AttackPlayer:
    """Plays back recorded attack sessions"""
    
    def __init__(self, attack_recorder: Optional[AttackRecorder] = None,
                 troop_bar_config: Optional[Dict] = None,
                 deployment_zone: Optional[Dict] = None):
        self.attack_recorder = attack_recorder if attack_recorder is not None else AttackRecorder()
        self.is_playing = False
        self.current_playback = None
        self.playback_thread = None
        self.playback_speed = 1.0
        self.slot_mapping: Dict[int, int] = {}

        # Troop bar and deployment zone configuration
        self._troop_bar_config = troop_bar_config or {}
        self._deployment_zone = deployment_zone  # Optional {x_min, y_min, x_max, y_max}
        
        print("Attack Player initialized")
        print("Playback Controls:")
        print("  F8 - Pause/Resume playback")
        print("  F9 - Stop playback")
        print("  ESC - Emergency stop")
    
    def play_attack(self, session_name: str, speed: float = 1.0, auto_mode: bool = False) -> bool:
        """Play back a recorded attack session"""
        if self.is_playing:
            print("Already playing an attack")
            return False
        
        # Load the recording
        recording = self.attack_recorder.load_recording(session_name)
        if not recording:
            print(f"Could not load recording: {session_name}")
            return False
        
        self.current_playback = recording
        self.playback_speed = speed
        self.is_playing = True
        
        print(f"\n=== PLAYING ATTACK SESSION: {session_name} ===")
        print(f"Duration: {recording.get('duration', 0):.1f} seconds")
        print(f"Actions: {len(recording.get('actions', []))}")
        print(f"Speed: {speed}x")

        # Build troop slot remapping before playback starts
        actions = recording.get('actions', [])
        self.slot_mapping = self._build_troop_slot_mapping(actions)
        
        if not auto_mode:
            print("\nStarting playback in 3 seconds...")
            print("Press F8 to pause, F9 to stop, ESC for emergency stop")
            time.sleep(3)
        else:
            print("\nStarting playback immediately (auto mode)...")
        
        # Start playback thread
        self.playback_thread = threading.Thread(
            target=self._playback_loop, 
            args=(recording.get('actions', []),)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
        return True
    
    def stop_playback(self) -> None:
        """Stop the current playback"""
        if not self.is_playing:
            print("No playback active")
            return
        
        print("Stopping playback")
        self.is_playing = False
        
        if self.playback_thread:
            self.playback_thread.join(timeout=2)
    
    def _playback_loop(self, actions: List[Dict]) -> None:
        """Main playback loop"""
        try:
            last_timestamp = 0
            paused = False
            
            for i, action in enumerate(actions):
                if not self.is_playing:
                    break
                
                # Check for control keys
                if keyboard.is_pressed('esc'):
                    print("\nEmergency stop activated")
                    break
                
                if keyboard.is_pressed('f9'):
                    print("\nPlayback stopped by user")
                    break
                
                if keyboard.is_pressed('f8'):
                    paused = not paused
                    status = "paused" if paused else "resumed"
                    print(f"\nPlayback {status}")
                    
                    # Wait for key release
                    while keyboard.is_pressed('f8'):
                        time.sleep(0.1)
                
                # Handle pause
                while paused and self.is_playing:
                    time.sleep(0.1)
                    if keyboard.is_pressed('f8'):
                        paused = False
                        print("Playback resumed")
                        while keyboard.is_pressed('f8'):
                            time.sleep(0.1)
                
                if not self.is_playing:
                    break
                
                # Calculate delay based on timestamps
                current_timestamp = action.get('timestamp', 0)
                if i > 0:
                    delay = (current_timestamp - last_timestamp) / self.playback_speed
                    if delay > 0:
                        time.sleep(humanize_delay(delay))
                
                # Execute the action
                self._execute_action(action)
                last_timestamp = current_timestamp
                
                # Progress indicator
                progress = (i + 1) / len(actions) * 100
                print(f"\rProgress: {progress:.1f}% ({i + 1}/{len(actions)})", end='', flush=True)
        
        except Exception as e:
            print(f"\nPlayback error: {e}")
        
        finally:
            self.is_playing = False
            print(f"\nPlayback completed")
    
    def set_troop_bar_config(self, cfg: Dict) -> None:
        """Update the troop bar configuration and reset the one-shot warning flag."""
        self._troop_bar_config = cfg
        self._config_warned = False

    def _get_troop_bar_bounds(self) -> Dict:
        """Get troop bar region bounds resolved against current screen size."""
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
                'slot_width': slot_width,
                'num_slots': num_slots,
            }

        # Smart defaults based on screen resolution when not yet calibrated.
        y_min_offset = cfg.get('y_min_offset', max(100, int(screen_height * 0.08)))
        num_slots = cfg.get('num_slots', 8)
        estimated_bar_width = max(1, int(screen_width * 0.45))
        slot_width = cfg.get('slot_width', estimated_bar_width // max(num_slots, 1))
        stored_x_start = cfg.get('x_start', 0)
        x_start = stored_x_start if stored_x_start != 0 else (screen_width - estimated_bar_width) // 2
        return {
            'y_min': screen_height - y_min_offset,
            'y_max': screen_height,
            'x_start': x_start,
            'slot_width': slot_width,
            'num_slots': num_slots,
        }

    def _validate_troop_bar_config(self) -> None:
        """Warn once if the troop bar config looks wrong for the current screen resolution."""
        if getattr(self, '_config_warned', False):
            return
        self._config_warned = True
        bounds = self._get_troop_bar_bounds()
        screen_width, _ = pyautogui.size()
        total_bar_width = bounds['num_slots'] * bounds['slot_width']
        if total_bar_width < screen_width * 0.1:
            print("⚠️ WARNING: Troop bar config seems too narrow for your screen resolution!")
            print(f"   Screen width: {screen_width}px, Troop bar width: {total_bar_width}px")
            print("   Run 'Calibrate Troop Bar' from the Auto Attack menu to fix this.")
        if bounds['x_start'] == 0 and screen_width > 1920:
            print("⚠️ WARNING: Troop bar x_start is 0 — this is likely wrong for your resolution!")
            print("   Run 'Calibrate Troop Bar' from the Auto Attack menu to fix this.")

    def _build_troop_slot_mapping(self, recording_actions: List[Dict]) -> Dict[int, int]:
        """
        Compare recorded troop icons with the current troop bar to build a slot
        remapping dictionary {original_slot_index: current_slot_index}.

        Uses OpenCV template matching against a live screenshot of the troop bar.
        Falls back to an empty mapping (identity) when matching is not possible.
        """
        if not _HAS_CV2 or not _HAS_PIL:
            return {}

        # Collect unique troop_select actions that have a saved icon
        troop_actions = [
            a for a in recording_actions
            if a.get('type') == 'troop_select' and a.get('troop_icon')
        ]
        if not troop_actions:
            return {}

        self._validate_troop_bar_config()
        bounds = self._get_troop_bar_bounds()
        num_slots = bounds['num_slots']
        slot_width = bounds['slot_width']
        x_start = bounds['x_start']
        y_min = bounds['y_min']
        bar_height = bounds['y_max'] - y_min

        print(f"🔍 Building troop slot mapping...")
        print(f"   Troop bar region: x={x_start}, y={y_min}, width={num_slots * slot_width}, height={bar_height}")
        print(f"   Number of slots: {num_slots}, slot width: {slot_width}px")
        print(f"   Found {len(troop_actions)} unique troop_select action(s) with icons")

        try:
            # Capture the current troop bar
            bar_screenshot = pyautogui.screenshot(
                region=(x_start, y_min, num_slots * slot_width, bar_height)
            )
            bar_img = cv2.cvtColor(np.array(bar_screenshot), cv2.COLOR_RGB2BGR)

            # Save debug screenshot so the user can verify the captured region
            os.makedirs("logs", exist_ok=True)
            debug_path = os.path.join("logs", "debug_troop_bar.png")
            bar_screenshot.save(debug_path)
            print(f"   Debug: troop bar screenshot saved to {debug_path}")
        except Exception as e:
            print(f"⚠️ Could not capture troop bar for slot mapping: {e}")
            return {}

        mapping: Dict[int, int] = {}
        seen_slots: set = set()

        for action in troop_actions:
            original_slot = action.get('slot_index', 0)
            if original_slot in mapping:
                continue

            icon_path = action.get('troop_icon', '')
            if not os.path.exists(icon_path):
                continue

            try:
                template = cv2.imread(icon_path)
                if template is None:
                    continue

                # Match template against bar image
                result = cv2.matchTemplate(bar_img, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= 0.7:
                    # Determine which slot the best match falls in
                    match_x = max_loc[0] + template.shape[1] // 2
                    new_slot = min(match_x // slot_width, num_slots - 1)
                    if new_slot not in seen_slots:
                        mapping[original_slot] = new_slot
                        seen_slots.add(new_slot)
                        print(f"🔄 Troop slot remapped: recorded slot {original_slot} → current slot {new_slot} (confidence {max_val:.2f})")
                    else:
                        print(f"⚠️ Slot {new_slot} already claimed; keeping slot {original_slot} as-is")
            except Exception as e:
                print(f"⚠️ Template matching failed for slot {original_slot}: {e}")

        if not mapping:
            print("⚠️ No troop slot remapping could be built!")
            print("   Possible causes:")
            print("   - Troop bar config doesn't match your screen (run 'Calibrate Troop Bar')")
            print("   - Troop icons from recording don't match current troops")
            print("   - opencv-python not installed")
        else:
            print(f"✅ Built {len(mapping)} slot remapping(s)")

        return mapping

    def _execute_action(self, action: Dict) -> None:
        """Execute a single action"""
        action_type = action.get('type', '')
        x = action.get('x', 0)
        y = action.get('y', 0)

        # Reject coordinates that fall outside the physical screen.
        if action_type in ('click', 'move', 'drag', 'troop_select'):
            screen_width, screen_height = pyautogui.size()
            if x < 0 or y < 0 or x >= screen_width or y >= screen_height:
                print(f" ⚠️ Skipping {action_type} at ({x}, {y}) — out of screen bounds")
                return

        try:
            if action_type == 'click':
                # Validate deployment clicks against the configured deployment zone
                if self._deployment_zone and not self._is_in_deployment_zone(x, y):
                    print(f" - ⚠️ Skipping click at ({x}, {y}): outside deployment zone")
                    return
                hx, hy = humanize_click(x, y)
                pyautogui.click(hx, hy)
                print(f" - Click at ({hx}, {hy})")

            elif action_type == 'troop_select':
                original_slot = action.get('slot_index', 0)
                bounds = self._get_troop_bar_bounds()
                if self.slot_mapping and original_slot in self.slot_mapping:
                    new_slot = self.slot_mapping[original_slot]
                    new_x = bounds['x_start'] + new_slot * bounds['slot_width'] + bounds['slot_width'] // 2
                    new_y = y
                    hx, hy = humanize_click(new_x, new_y)
                    pyautogui.click(hx, hy)
                    print(f" - Troop select: slot {original_slot} → slot {new_slot} at ({hx}, {hy})")
                else:
                    hx, hy = humanize_click(x, y)
                    pyautogui.click(hx, hy)
                    print(f" - Troop select: slot {original_slot} at ({hx}, {hy}) (no remap)")
            
            elif action_type == 'move':
                hx, hy = humanize_click(x, y)
                pyautogui.moveTo(hx, hy)
                print(f" - Move to ({hx}, {hy})")
            
            elif action_type == 'delay':
                duration = action.get('duration', 1.0) / self.playback_speed
                time.sleep(humanize_delay(duration))
                print(f" - Delay {duration:.1f}s")
            
            elif action_type == 'drag':
                start_x = action.get('start_x', x)
                start_y = action.get('start_y', y)
                hx, hy = humanize_click(x, y)
                hsx, hsy = humanize_click(start_x, start_y)
                pyautogui.drag(hx - hsx, hy - hsy, duration=0.5)
                print(f" - Drag from ({hsx}, {hsy}) to ({hx}, {hy})")
            
            else:
                print(f" - Unknown action: {action_type}")
        
        except Exception as e:
            print(f" - Error executing action {action_type}: {e}")

    def _is_in_deployment_zone(self, x: int, y: int) -> bool:
        """Return True if the coordinate is within the configured deployment zone."""
        dz = self._deployment_zone
        if not dz:
            return True
        screen_width, screen_height = pyautogui.size()
        return (dz.get('x_min', 0) <= x <= dz.get('x_max', screen_width) and
                dz.get('y_min', 0) <= y <= dz.get('y_max', screen_height))
    
    def validate_recording(self, session_name: str) -> Dict[str, any]:
        """Validate a recording before playback"""
        recording = self.attack_recorder.load_recording(session_name)
        if not recording:
            return {'valid': False, 'error': 'Recording not found'}
        
        actions = recording.get('actions', [])
        if not actions:
            return {'valid': False, 'error': 'No actions in recording'}
        
        # Check screen bounds
        screen_width, screen_height = pyautogui.size()
        out_of_bounds = []
        
        for i, action in enumerate(actions):
            x, y = action.get('x', 0), action.get('y', 0)
            if not (0 <= x < screen_width and 0 <= y < screen_height):
                out_of_bounds.append((i, x, y))
        
        result = {
            'valid': len(out_of_bounds) == 0,
            'total_actions': len(actions),
            'duration': recording.get('duration', 0),
            'out_of_bounds': out_of_bounds
        }
        
        if out_of_bounds:
            result['error'] = f"{len(out_of_bounds)} actions are out of screen bounds"
        
        return result
    
    def preview_recording(self, session_name: str) -> None:
        """Show a preview of the recording actions"""
        recording = self.attack_recorder.load_recording(session_name)
        if not recording:
            print(f"Recording not found: {session_name}")
            return
        
        actions = recording.get('actions', [])
        
        print(f"\n=== RECORDING PREVIEW: {session_name} ===")
        print(f"Duration: {recording.get('duration', 0):.1f} seconds")
        print(f"Total actions: {len(actions)}")
        
        # Show action summary
        action_counts = {}
        for action in actions:
            action_type = action.get('type', 'unknown')
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        
        print("\nAction breakdown:")
        for action_type, count in action_counts.items():
            print(f"  {action_type}: {count}")
        
        # Show first few actions
        print(f"\nFirst 10 actions:")
        for i, action in enumerate(actions[:10]):
            timestamp = action.get('timestamp', 0)
            action_type = action.get('type', 'unknown')
            x, y = action.get('x', 0), action.get('y', 0)
            print(f"  {i+1:2d}. {timestamp:6.1f}s - {action_type} at ({x}, {y})")
        
        if len(actions) > 10:
            print(f"  ... and {len(actions) - 10} more actions")
    
    def set_playback_speed(self, speed: float) -> None:
        """Set the playback speed multiplier"""
        if speed <= 0:
            print("Speed must be positive")
            return
        
        self.playback_speed = speed
        print(f"Playback speed set to {speed}x") 