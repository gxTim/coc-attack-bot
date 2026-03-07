"""
Logger - Logging utility for the COC Attack Bot
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Callable, Optional

class Logger:
    """Simple logging utility for the COC Attack Bot"""
    
    def __init__(self, log_file: Optional[str] = None, console_output: bool = True,
                 max_log_age_days: int = 7):
        self.log_dir = "logs"
        self._gui_callback: Optional[Callable[[str, str], None]] = None
        self._console_output = console_output
        
        # Create logs directory
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Set default log file if not provided — each session gets its own file
        # using date+time so restarts never share a file.
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"coc_bot_{timestamp}.log"
        
        self.log_file = os.path.join(self.log_dir, log_file)
        
        # Remove log files older than max_log_age_days
        self._cleanup_old_logs(max_log_age_days)
        
        # Configure logging
        self._setup_logging()
        
        # Write a clear session-start marker so session boundaries are visible
        # even if the caller later reads files from the same directory.
        self.logger.info("═══ SESSION START ═══")
        self.info("Logger initialized")
    
    def _cleanup_old_logs(self, max_age_days: int) -> None:
        """Delete log files older than *max_age_days* from the log directory."""
        if max_age_days <= 0:
            return
        cutoff = datetime.now() - timedelta(days=max_age_days)
        try:
            for filename in os.listdir(self.log_dir):
                if not filename.startswith("coc_bot_") or not filename.endswith(".log"):
                    continue
                filepath = os.path.join(self.log_dir, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if mtime < cutoff:
                        os.remove(filepath)
                except OSError:
                    pass
        except OSError:
            pass

    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Use a unique logger name per instance to avoid handler duplication
        # when multiple Logger objects are created in the same process.
        self.logger = logging.getLogger(f'COCBot.{id(self)}')
        self.logger.setLevel(logging.DEBUG)
        # Propagation to the root logger is disabled so that duplicate
        # messages are not produced by ancestor handlers.
        self.logger.propagate = False
        
        # Create file handler — keep a reference for explicit cleanup
        self._file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        self._file_handler.setLevel(logging.DEBUG)
        self._file_handler.setFormatter(formatter)
        self.logger.addHandler(self._file_handler)
        
        # Create console handler (only when console output is enabled)
        if self._console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def debug(self, message: str) -> None:
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message: str) -> None:
        """Log info message"""
        self.logger.info(message)
        if self._gui_callback:
            self._gui_callback(message, "INFO")
    
    def warning(self, message: str) -> None:
        """Log warning message"""
        self.logger.warning(message)
        if self._gui_callback:
            self._gui_callback(message, "WARNING")
    
    def error(self, message: str) -> None:
        """Log error message"""
        self.logger.error(message)
        if self._gui_callback:
            self._gui_callback(message, "ERROR")
    
    def critical(self, message: str) -> None:
        """Log critical message"""
        self.logger.critical(message)
        if self._gui_callback:
            self._gui_callback(message, "CRITICAL")
    
    def log_action(self, action: str, details: str = "") -> None:
        """Log bot action"""
        message = f"BOT ACTION: {action}"
        if details:
            message += f" - {details}"
        self.info(message)
    
    def log_recording(self, session_name: str, action_count: int, duration: float) -> None:
        """Log recording completion"""
        self.info(f"RECORDING COMPLETE: {session_name} - {action_count} actions, {duration:.1f}s")
    
    def log_playback(self, session_name: str, status: str) -> None:
        """Log playback status"""
        self.info(f"PLAYBACK {status.upper()}: {session_name}")
    
    def log_coordinate_mapping(self, name: str, x: int, y: int) -> None:
        """Log coordinate mapping"""
        self.info(f"COORDINATE MAPPED: {name} at ({x}, {y})")
    
    def get_log_file_path(self) -> str:
        """Get the current log file path"""
        return self.log_file
    
    def set_gui_callback(self, callback: Optional[Callable[[str, str], None]]) -> None:
        """Set a callback for routing log messages to the GUI panel.
        
        The callback receives (message, level) where level is one of:
        'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
        Pass None to remove the callback.
        """
        self._gui_callback = callback

    def close(self) -> None:
        """Flush and close the file handler to release the log file."""
        if hasattr(self, '_file_handler') and self._file_handler is not None:
            self._file_handler.close()
            self.logger.removeHandler(self._file_handler)
            self._file_handler = None 