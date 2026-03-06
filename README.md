# COC Attack Bot

A Windows automation bot for Clash of Clans that can record attack sessions and replay them automatically. Features a modern dark-themed GUI, AI-powered base analysis via Google Gemini, and built-in anti-ban measures.

## ⚠️ Disclaimer

This bot is for educational purposes only. Use at your own risk. The author is not responsible for any account bans or other consequences that may result from using this software.

## Features

- 🖥️ **Modern GUI** - Dark-themed CustomTkinter interface with dashboard, recording, and auto-attack pages
- 🎯 **Coordinate Mapping** - Record button positions for your screen resolution
- 📹 **Attack Recording** - Record your attack sessions including clicks and timing
- ▶️ **Attack Playback** - Replay recorded attacks automatically
- 🤖 **AI Base Analysis** - Analyze base loot and Town Hall level using Google Gemini AI
- 🏃 **Auto Attacker** - Automatically find and attack bases based on loot requirements
- 🛡️ **Anti-Ban System** - Humanized clicks, random delays, cooldowns, and session breaks
- 🖼️ **Screenshot Capture** - Take screenshots of the game window
- 🎮 **Game Detection** - Automatically detect COC game window
- ⌨️ **Hotkey Controls** - Easy hotkey controls for all functions
- 📊 **Live Dashboard** - Real-time attack statistics, loot totals, and success rates
- 💾 **Session Management** - Save, load, and manage multiple attack sessions
- ⚙️ **JSON Configuration** - Simple `config.json` for all settings

## Requirements

- Windows 10 or later
- Python 3.10 or later
- **Clash of Clans running in FULL SCREEN mode** (required for all operations)
- Compatible with emulators (BlueStacks, NoxPlayer, etc.)
- Google Gemini API key (optional — for AI analysis features)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/gxTim/coc-attack-bot.git
   cd coc-attack-bot
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the bot:**
   ```bash
   copy config.example.json config.json
   ```
   Open `config.json` in a text editor and adjust settings as needed (see [Configuration](#configuration)).

4. **Run the bot:**

   | Method | Command | Description |
   |--------|---------|-------------|
   | **GUI (recommended)** | Double-click `start_bot.bat` or `main.pyw` | Launches the GUI without a console window |
   | **GUI + console** | `python main.py` | GUI with log output in the console |
   | **Console only** | `python main.py --console` | Text-based menu interface |
   | **Auto-launcher** | Double-click `run_bot.bat` | Checks dependencies, then launches |

## Quick Start Guide

**⚠️ IMPORTANT: Always run Clash of Clans in FULL SCREEN mode during all operations!**

### 1. Initial Setup

1. Open Clash of Clans in **full screen mode**
2. Start the bot (see table above)
3. Use **Game Detection** to verify the bot can find your game window
4. Take a test screenshot to confirm the capture area

### 2. Map Key Coordinates

Map the button positions for your specific screen resolution:

1. Open the **Coordinate Mapping** page (GUI) or select it from the console menu
2. Press **F1** to start mapping mode
3. Move your mouse to each game element and press **F2** to record:
   - `attack_button` — starts base search
   - `next_button` — skip to next base
   - `find_a_match` — find a match button
   - `return_home` — return home after attack
4. Press **F3** to save all coordinates

### 3. Record Attack Strategies

1. Open the **Recording** page
2. Enter a name for the strategy (e.g. `barch_raid`)
3. Press **F5** to start recording
4. Play through a full attack — clicks are recorded automatically
5. Use **F7** to add manual delay markers
6. Press **F5** again to stop and save

### 4. Auto Attack (AI-Powered)

1. Add your Gemini API key in `config.json` → `ai_analyzer.google_gemini_api_key`
2. Open the **Auto Attack** page
3. Select one or more recorded attack sessions
4. Set minimum loot requirements (gold, elixir, dark elixir)
5. Set max Town Hall level
6. Click **▶ Start Auto Attack**

The bot will search for bases, analyze loot with AI, attack qualifying bases, and repeat.

## Controls

| Context | Key | Action |
|---------|-----|--------|
| Coordinate Mapping | **F1** | Start / Stop mapping mode |
| | **F2** | Record current mouse position |
| | **F3** | Save coordinates |
| | **ESC** | Cancel mapping |
| Attack Recording | **F5** | Start / Stop recording |
| | **F6** | Manual click recording |
| | **F7** | Add delay marker |
| | **ESC** | Cancel recording |
| Attack Playback | **F8** | Pause / Resume |
| | **F9** | Stop playback |
| | **ESC** | Emergency stop |
| Global | **Ctrl+Alt+S** | Emergency stop (auto attack) |
| | Mouse to top-left corner | PyAutoGUI failsafe stop |

## Directory Structure

```
coc-attack-bot/
├── main.py                 # Entry point (GUI default, --console flag)
├── main.pyw                # Windows GUI launcher (no console)
├── start_bot.bat           # Quick-launch GUI (no console)
├── start_bot_console.bat   # Quick-launch console mode
├── run_bot.bat             # Auto-install + launch
├── config.example.json     # Example configuration
├── config.json             # Your local configuration (not tracked)
├── requirements.txt        # Python dependencies
├── example_usage.py        # Scripted usage examples
├── src/
│   ├── bot_controller.py   # Main bot logic controller
│   ├── core/
│   │   ├── ai_analyzer.py        # Google Gemini AI loot analysis
│   │   ├── attack_player.py      # Attack playback engine
│   │   ├── attack_recorder.py    # Attack session recording
│   │   ├── auto_attacker.py      # Automated attack loop
│   │   ├── coordinate_mapper.py  # Button coordinate mapping
│   │   └── screen_capture.py     # Screenshot and window detection
│   ├── ui/
│   │   ├── gui.py          # CustomTkinter GUI (dashboard, auto-attack, recording)
│   │   └── console_ui.py   # Console-based menu interface
│   └── utils/
│       ├── config.py       # JSON configuration management
│       ├── logger.py       # Logging utility
│       └── humanizer.py    # Anti-ban click/delay randomization
├── coordinates/            # Saved button coordinates
├── recordings/             # Recorded attack sessions
├── screenshots/            # Captured screenshots
└── logs/                   # Log files
```

## Configuration

All settings live in `config.json` (copy from `config.example.json`). Key sections:

### Bot Settings
```json
"bot": {
    "click_delay": 0.1,
    "playback_speed": 1.0,
    "failsafe": true
}
```

### AI Analyzer
```json
"ai_analyzer": {
    "enabled": false,
    "google_gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "model": "gemini-2.5-flash-lite",
    "min_gold": 300000,
    "min_elixir": 300000,
    "min_dark_elixir": 2000
}
```
Get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey).

### Anti-Ban
```json
"anti_ban": {
    "enabled": true,
    "click_offset_range": 5,
    "delay_variance": 0.3,
    "cooldown_min": 10,
    "cooldown_max": 45,
    "max_attacks_per_hour": 20,
    "max_attacks_per_session": 100,
    "break_every_n_attacks": 10,
    "break_duration_min": 120,
    "break_duration_max": 300
}
```

### Auto Attacker
```json
"auto_attacker": {
    "attack_sessions": [],
    "max_search_attempts": 10,
    "battle_timeout": 180,
    "max_th_level": 16,
    "troop_bar": { ... }
}
```

## Tips for Best Results

1. **Full Screen Mode** — always run COC in full screen for accurate coordinates
2. **Consistent Resolution** — don't change resolution between recording and playback
3. **Game State** — make sure COC is in the same state when replaying attacks
4. **Accurate Mapping** — take time to map all essential buttons precisely
5. **Test First** — try recordings on practice attacks before going live
6. **Supervision** — always supervise the bot during operation
7. **Army Ready** — make sure your army is trained before auto-attacking
8. **Stable Internet** — required for AI analysis features
9. **Anti-Ban Settings** — keep the defaults unless you know what you're doing

## Safety Features

- **Failsafe** — move mouse to top-left corner to stop all automation
- **Emergency Stop** — `Ctrl+Alt+S` during auto attack, or `ESC` during any operation
- **Anti-Ban** — randomized clicks, delays, cooldowns, and session breaks
- **Validation** — recordings are validated before playback
- **Logging** — all actions are logged to `logs/` for debugging

## Troubleshooting

### GUI doesn't start / "customtkinter not installed"
```bash
python -m pip install customtkinter
```
Make sure `pip` installs into the same Python version you run.

### Game Not Detected
- Make sure COC is running and visible on screen
- Try full screen vs. windowed mode
- Check if you're using a supported emulator

### Playback Issues
- Re-map coordinates if your resolution changed
- Verify game state matches the recording
- Try slower playback speed in `config.json`

### Console window stays open with GUI
- Use `start_bot.bat`, `main.pyw`, or `pythonw main.py` instead of `python main.py`

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

This project is provided as-is for educational purposes. Use responsibly and at your own risk.

---

**Remember: This bot is for educational purposes only. Always follow the game's terms of service and use responsibly.**
 