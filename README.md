# krakbot

A cross-platform, interactive scalping bot for Kraken.
- Prompts for API credentials (stored securely).
- Wizard for trading parameters with sensible defaults.
- Preset saving/loading.
- Graceful shutdown with final purchase.
- Colorized, transparent logging.

## Installation

```bash
git clone https://github.com/ljpremo/krakbot.git
cd krakbot
python3 setup.py
```

## Usage

```bash
python3 krakbot.py
```

Follow the interactive prompts to configure and start the bot.

## Configuration

- API credentials are stored in your system keyring.
- Presets saved in `~/.config/krakbot/preset.json` (Linux/macOS) or `%APPDATA%/krakbot/preset.json` (Windows).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
