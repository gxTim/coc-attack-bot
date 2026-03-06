#!/usr/bin/env python3
"""
COC Attack Bot - Main Entry Point
Automated Clash of Clans attack recording and playback bot for Windows
"""

import sys
import traceback
from src.bot_controller import BotController


def main():
    """Main entry point for the COC Attack Bot"""
    use_console = '--console' in sys.argv

    try:
        # Initialize bot controller (suppress console output in GUI mode)
        bot = BotController(console_output=use_console)
        bot.logger.info("Starting COC Attack Bot...")

        if use_console:
            from src.ui.console_ui import ConsoleUI
            ui = ConsoleUI(bot)
            ui.run()
        else:
            try:
                from src.ui.gui import BotGUI
                gui = BotGUI(bot)
                gui.run()
            except ImportError:
                traceback.print_exc()
                print("⚠️  customtkinter not installed. Falling back to console UI.")
                print("Install with: pip install customtkinter")
                from src.ui.console_ui import ConsoleUI
                ui = ConsoleUI(bot)
                ui.run()

    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
