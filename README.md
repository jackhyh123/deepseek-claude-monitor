# DeepSeek Monitor

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS-blue" alt="platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
  <img src="https://img.shields.io/badge/zero--invasion-✓-brightgreen" alt="zero-invasion">
</p>

<p align="center">
  <b>macOS menu bar monitor for DeepSeek token usage with Claude Code</b><br>
  <sub>Real-time cost tracking · DeepSeek balance checker · Web dashboard</sub>
</p>

---

## Why?

When using DeepSeek as the inference backend for Claude Code (3P mode), there's **no built-in way** to see how many tokens you've consumed or how much money you've spent. This tool solves that.

**Zero-invasion approach**: reads Claude Code's JSONL session files directly — no proxy, no config changes, no risk of breaking your Claude connection.

## Features

- 📊 **Real-time menu bar** — Today's cost + DeepSeek balance at a glance
- 🌐 **Web dashboard** — `http://localhost:8899` shows detailed token stats
- 💰 **Cost calculation** — Supports all DeepSeek models with correct pricing
- 🔋 **Balance checking** — Reads your DeepSeek API key and shows remaining balance
- 0️⃣ **Zero invasion** — Reads Claude Code's own JSONL files, no proxy or config changes
- 🍎 **Native macOS app** — Lives in your menu bar and `/Applications`

## Screenshots

```
┌─────────────────────────┐
│  DS ¥1.51 | ¥98.50      │  ← Menu bar: cost | balance
├─────────────────────────┤
│  今日请求: 603 次        │
│  今日 Token: 1,266,675   │
│  今日费用: ¥1.5088       │
│  ─────────────────────  │
│  本月费用: ¥1.5088       │
│  余额: ¥100 (充值¥90...) │
│  ─────────────────────  │
│  🌐 打开仪表盘           │
│  🔄 刷新余额             │
│  ─────────────────────  │
│  退出                    │
└─────────────────────────┘
```

## Requirements

- **macOS** (tested on Ventura+)
- **Python 3.9+** with pip
- **Claude Code** with DeepSeek 3P mode configured

## Quick Install

```bash
git clone https://github.com/jackhyh123/deepseek-claude-monitor.git
cd deepseek-claude-monitor
bash install.sh
```

That's it. The app will appear in your menu bar and `/Applications`.

## Manual Setup

```bash
# 1. Install dependencies
pip3 install rumps requests pillow

# 2. Run monitor
python3 monitor.py
```

Optional: build the .app bundle manually:

```bash
python3 generate_icon.py .
iconutil -c icns ds_icon.iconset -o ds_icon.icns

osacompile -o "/Applications/DeepSeek Monitor.app" \
  -e 'do shell script "python3 /path/to/monitor.py > /tmp/ds-monitor.log 2>&1 &"'
```

## How It Works

```
Claude Code → writes JSONL session files → ~/.claude/projects/
                                              ↓
DeepSeek Monitor ← tail JSONL ← extracts token usage ← SQLite DB
       ↓
  ┌────┴────┐
  Menu Bar   Dashboard (localhost:8899)
```

### Token Detection

Monitors `~/.claude/projects/**/*.jsonl` for entries with `type: "assistant"` that contain `message.usage` (input_tokens, output_tokens). Uses `message.id` for deduplication.

### Pricing

| Model | Input (¥/1M tokens) | Output (¥/1M tokens) |
|-------|---------------------|----------------------|
| deepseek-chat / v3 / v4-pro | ¥1.00 | ¥2.00 |
| deepseek-reasoner / r1 | ¥4.00 | ¥16.00 |

### Balance

Reads API key from `~/Library/Application Support/Claude-3p/configLibrary/*.json` (3P mode config) or `DEEPSEEK_API_KEY` env var.

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | (auto-detect) | DeepSeek API key |
| `DS_MONITOR_PORT` | `8899` | Dashboard port |
| `DS_MONITOR_DB` | `~/.deepseek-monitor/usage.db` | SQLite database path |

## Project Structure

```
deepseek-claude-monitor/
├── monitor.py           # Main application
├── generate_icon.py     # Icon generator (Pillow)
├── install.sh           # One-click installer
├── LICENSE              # MIT
└── README.md            # This file
```

## FAQ

**Q: Does this modify my Claude Code config?**
No. It only reads JSONL files. Zero files are written to Claude's directories.

**Q: Will it break my Claude connection?**
No. Unlike proxy-based approaches, this reads files passively.

**Q: How much delay?**
5-10 seconds. The monitor tails JSONL files every 5 seconds.

**Q: Does it work with other LLM providers?**
Currently only DeepSeek pricing is configured, but the JSONL format is provider-agnostic. PRs welcome for other providers.

## License

MIT © 2026 jackhyh123
