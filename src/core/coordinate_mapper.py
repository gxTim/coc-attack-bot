"""
Coordinate Mapper - Records and manages button coordinates for the COC bot
"""

import json
import os
import time
import pyautogui
import keyboard
from typing import Dict, Optional


class CoordinateMapper:
    """Records and manages button coordinates for automated clicking"""
    
    def __init__(self, logger=None):
        self.coordinates_dir = "coordinates"
        self.coordinates_file = os.path.join(self.coordinates_dir, "button_coordinates.json")
        self.coordinates = {}
        self.is_mapping = False
        self._logger = logger
        
        # Create coordinates directory
        os.makedirs(self.coordinates_dir, exist_ok=True)
        
        # Load existing coordinates
        self.load_coordinates()
        
        self._log("Coordinate Mapper initialized")
        self._log("Mapping Controls:")
        self._log("  F1 - Start/Stop coordinate mapping")
        self._log("  F2 - Record current mouse position")
        self._log("  F3 - Save coordinates")
        self._log("  ESC - Cancel mapping")

    def _log(self, msg: str, level: str = "info") -> None:
        """Log via Logger if available, otherwise print."""
        if self._logger:
            getattr(self._logger, level)(msg)
        else:
            print(msg)
    
    def load_coordinates(self) -> None:
        """Load coordinates from file"""
        if os.path.exists(self.coordinates_file):
            try:
                with open(self.coordinates_file, 'r') as f:
                    self.coordinates = json.load(f)
                self._log(f"Loaded {len(self.coordinates)} coordinate mappings")
            except Exception as e:
                self._log(f"Error loading coordinates: {e}", "error")
                self.coordinates = {}
        else:
            self._log("No existing coordinates file found")
    
    def save_coordinates(self, name: Optional[str] = None, coords: Optional[Dict] = None) -> None:
        """Save coordinates to file"""
        try:
            if coords:
                # Save specific coordinates
                if name:
                    self.coordinates[name] = coords
                else:
                    self.coordinates.update(coords)
            
            with open(self.coordinates_file, 'w') as f:
                json.dump(self.coordinates, f, indent=2)
            
            self._log(f"Coordinates saved to {self.coordinates_file}")
            self._log(f"Total mappings: {len(self.coordinates)}")
        except Exception as e:
            self._log(f"Error saving coordinates: {e}", "error")
    
    def start_mapping(self, prompt_callback=None) -> None:
        """Start interactive coordinate mapping.

        Args:
            prompt_callback: Optional callable(x, y) -> str | None.
                When provided it is called instead of ``input()`` whenever F2
                is pressed to ask the user for a button name.  Return ``None``
                (or an empty string) to skip recording that position.
                If no callback is supplied the method falls back to ``input()``
                for console-mode compatibility.
        """
        if self.is_mapping:
            self._log("Already in mapping mode")
            return
        
        self.is_mapping = True
        current_session = {}
        
        self._log("\n=== COORDINATE MAPPING MODE ===")
        self._log("Instructions:")
        self._log("1. Move mouse to the button you want to map")
        self._log("2. Press F2 to record the position")
        self._log("3. Enter a name for the button")
        self._log("4. Repeat for all buttons")
        self._log("5. Press F3 to save all mappings")
        self._log("6. Press ESC to cancel")
        self._log("\nStarting in 3 seconds...")
        time.sleep(3)
        
        try:
            while self.is_mapping:
                if keyboard.is_pressed('esc'):
                    self._log("\nMapping cancelled")
                    break
                
                if keyboard.is_pressed('f2'):
                    # Record current mouse position
                    x, y = pyautogui.position()
                    if prompt_callback is not None:
                        raw = prompt_callback(x, y)
                        button_name = raw.strip() if raw else ""
                    else:
                        button_name = input(f"\nMouse at ({x}, {y}). Enter button name: ").strip()
                    
                    if button_name:
                        current_session[button_name] = {"x": x, "y": y}
                        self._log(f"Recorded '{button_name}' at ({x}, {y})")
                        self._log(f"Session mappings: {len(current_session)}")
                    
                    # Wait for key release
                    while keyboard.is_pressed('f2'):
                        time.sleep(0.1)
                
                if keyboard.is_pressed('f3'):
                    # Save current session
                    if current_session:
                        self.coordinates.update(current_session)
                        self.save_coordinates()
                        self._log(f"\nSaved {len(current_session)} new mappings")
                        current_session.clear()
                    else:
                        self._log("\nNo mappings to save")
                    
                    # Wait for key release
                    while keyboard.is_pressed('f3'):
                        time.sleep(0.1)
                
                if keyboard.is_pressed('f1'):
                    # Toggle mapping mode
                    self._log("\nExiting mapping mode")
                    break
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            self._log("\nMapping interrupted")
        
        finally:
            self.is_mapping = False
            self._log("Coordinate mapping stopped")
            
            # Save any remaining mappings
            if current_session:
                if prompt_callback is not None:
                    # GUI mode: auto-save without blocking on input()
                    self.coordinates.update(current_session)
                    self.save_coordinates()
                else:
                    response = input(f"Save {len(current_session)} unsaved mappings? (y/n): ").strip().lower()
                    if response == 'y':
                        self.coordinates.update(current_session)
                        self.save_coordinates()
    
    def get_coordinates(self, button_name: Optional[str] = None) -> Dict:
        """Get coordinates for a specific button or all buttons.

        When called without arguments, returns the internal dictionary directly
        for read-only access (no copy).  Callers must not mutate the returned
        dict; use :py:meth:`add_coordinate` or :py:meth:`remove_coordinate` to
        modify mappings.
        """
        if button_name:
            return self.coordinates.get(button_name, {})
        return self.coordinates
    
    def add_coordinate(self, name: str, x: int, y: int) -> None:
        """Add a single coordinate mapping"""
        self.coordinates[name] = {"x": x, "y": y}
        self._log(f"Added coordinate '{name}' at ({x}, {y})")
    
    def remove_coordinate(self, name: str) -> bool:
        """Remove a coordinate mapping"""
        if name in self.coordinates:
            del self.coordinates[name]
            self.save_coordinates()
            self._log(f"Removed coordinate '{name}'")
            return True
        else:
            self._log(f"Coordinate '{name}' not found")
            return False
    
    def list_coordinates(self) -> None:
        """Print all mapped coordinates"""
        if not self.coordinates:
            self._log("No coordinates mapped yet")
            return
        
        self._log("\n=== MAPPED COORDINATES ===")
        for name, coords in self.coordinates.items():
            self._log(f"  {name}: ({coords['x']}, {coords['y']})")
        self._log(f"Total: {len(self.coordinates)} mappings")
    
    def validate_coordinates(self) -> Dict[str, bool]:
        """Validate that all coordinates are within screen bounds"""
        screen_width, screen_height = pyautogui.size()
        validation = {}
        
        for name, coords in self.coordinates.items():
            x, y = coords['x'], coords['y']
            is_valid = 0 <= x < screen_width and 0 <= y < screen_height
            validation[name] = is_valid
            
            if not is_valid:
                self._log(f"WARNING: Coordinate '{name}' ({x}, {y}) is outside screen bounds", "warning")
        
        return validation
    
    def export_coordinates(self, filepath: str) -> None:
        """Export coordinates to a custom file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.coordinates, f, indent=2)
            self._log(f"Coordinates exported to {filepath}")
        except Exception as e:
            self._log(f"Error exporting coordinates: {e}", "error")
    
    def import_coordinates(self, filepath: str, merge: bool = True) -> None:
        """Import coordinates from a file"""
        try:
            with open(filepath, 'r') as f:
                imported_coords = json.load(f)
            
            if merge:
                self.coordinates.update(imported_coords)
                self._log(f"Merged {len(imported_coords)} coordinates")
            else:
                self.coordinates = imported_coords
                self._log(f"Replaced with {len(imported_coords)} coordinates")
            
            self.save_coordinates()
        except Exception as e:
            self._log(f"Error importing coordinates: {e}", "error") 