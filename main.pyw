#!/usr/bin/env python3
"""
COC Attack Bot - Windows GUI Launcher (no console window)
Double-click this file to start the bot with the GUI only.
"""
import sys
sys.argv = [__file__]  # Reset argv so --console is never set

from main import main
main()
