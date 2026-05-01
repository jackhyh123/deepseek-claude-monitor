#!/usr/bin/env python3
"""
DeepSeek Menu Bar Monitor for macOS — Zero-Invasion

零侵入: 直接从 Claude Code 的 JSONL 会话文件中读取 token 用量。
不改任何 Claude 配置, 不会断连。

菜单栏显示实时消耗 + DeepSeek 余额。
可选仪表盘: http://localhost:8899
"""

import os
import sys
import json
import time
import sqlite3
import threading
import hashlib
import webbrowser
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler

import rumps
import requests

# ── Config ──────────────────────────────────────────────
DB_PATH = os.environ.get("DS_MONITOR_DB", os.path.expanduser("~/.deepseek-monitor/usage.db"))
PORT = int(os.environ.get("DS_MONITOR_PORT", "8899"))
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
BALANCE_INTERVAL = 300
TAIL_INTERVAL = 5

PRICING = {
    "deepseek-chat":     (1, 2),
    "deepseek-reasoner": (4, 16),
    "deepseek-v3":       (1, 2),
    "deepseek-r1":       (4, 16),
    "deepseek-v4-pro":   (1, 2),
}

# ── Database ─────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        model TEXT,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        msg_uuid TEXT UNIQUE
    )""")
    # Migration: add msg_uuid if missing
    try:
        conn.execute("SELECT msg_uuid FROM requests LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE requests ADD COLUMN msg_uuid TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON requests(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg ON requests(msg_uuid)")
    conn.commit()
    conn.close()


def save_usage(model, prompt_tokens, completion_tokens, msg_uuid):
    if not msg_uuid:
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO requests (timestamp, model, prompt_tokens, completion_tokens, total_tokens, msg_uuid) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(), model, prompt_tokens, completion_tokens,
             prompt_tokens + completion_tokens, msg_uuid))
        conn.commit()
        inserted = conn.total_changes > 0
        conn.close()
        return inserted
    except Exception:
        conn.close()
        return False


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    today = date.today().isoformat()
    m = date.today().strftime("%Y-%m")

    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0), COALESCE(SUM(total_tokens),0) FROM requests WHERE date(timestamp)=?",
        (today,)).fetchone()
    mrow = conn.execute(
        "SELECT COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0), COALESCE(SUM(total_tokens),0) FROM requests WHERE strftime('%Y-%m', timestamp)=?",
        (m,)).fetchone()

    cost_today = 0.0
    for model, p, c in conn.execute(
            "SELECT model, SUM(prompt_tokens), SUM(completion_tokens) FROM requests WHERE date(timestamp)=? GROUP BY model",
            (today,)).fetchall():
        pr = PRICING.get(model, (1, 2))
        cost_today += (p / 1_000_000) * pr[0] + (c / 1_000_000) * pr[1]

    cost_month = 0.0
    for model, p, c in conn.execute(
            "SELECT model, SUM(prompt_tokens), SUM(completion_tokens) FROM requests WHERE strftime('%Y-%m', timestamp)=? GROUP BY model",
            (m,)).fetchall():
        pr = PRICING.get(model, (1, 2))
        cost_month += (p / 1_000_000) * pr[0] + (c / 1_000_000) * pr[1]

    recent = conn.execute(
        "SELECT timestamp, model, prompt_tokens, completion_tokens, total_tokens FROM requests ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()

    return {
        "today": {"requests": row[0], "prompt": row[1], "completion": row[2], "total": row[3], "cost": round(cost_today, 4)},
        "month": {"prompt": mrow[0], "completion": mrow[1], "total": mrow[2], "cost": round(cost_month, 4)},
        "recent": [{"ts": r[0], "model": r[1], "prompt": r[2], "completion": r[3], "total": r[4]} for r in recent],
    }


# ── JSONL Tailing ───────────────────────────────────────
# Track file position per JSONL to avoid re-reading old data
_file_positions: dict[str, int] = {}


def _file_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()[:12]


def _find_jsonl_files() -> list[str]:
    files = []
    if not os.path.isdir(PROJECTS_DIR):
        return files
    for root, _dirs, fnames in os.walk(PROJECTS_DIR):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                files.append(os.path.join(root, fn))
    return files


def tail_jsonl() -> int:
    """Scan JSONL files for new usage data. Returns number of new entries found."""
    files = _find_jsonl_files()
    new_count = 0

    for fp in files:
        if not os.path.exists(fp):
            continue
        fid = _file_id(fp)
        mtime = os.path.getmtime(fp)

        # Only process files modified in last 10 minutes (active sessions)
        if time.time() - mtime > 600:
            continue

        # Read from last known position
        start_pos = _file_positions.get(fid, 0)
        try:
            fsize = os.path.getsize(fp)
            if fsize <= start_pos:
                continue
            with open(fp, "rb") as f:
                f.seek(start_pos)
                raw = f.read()
                _file_positions[fid] = fsize
        except Exception:
            continue

        # Parse each line
        for line in raw.decode("utf-8", errors="ignore").split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue

            msg = entry.get("message", {})
            usage = msg.get("usage", {})
            if not usage:
                continue

            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            if input_tokens == 0 and output_tokens == 0:
                continue

            model = msg.get("model", "unknown")
            msg_id = msg.get("id", entry.get("uuid", ""))

            if save_usage(model, input_tokens, output_tokens, msg_id):
                new_count += 1

    return new_count


# ── Balance Checker ─────────────────────────────────────
class BalanceState:
    api_key: str = ""
    balance: str = "…"
    lock = threading.Lock()


bal_state = BalanceState()


def _load_api_key() -> str:
    """Try to find the DeepSeek API key."""
    # 1. From environment
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key

    # 2. From Claude-3p config
    config_path = os.path.expanduser(
        "Library/Application Support/Claude-3p/configLibrary/"
    )
    try:
        if os.path.isdir(config_path):
            for fn in os.listdir(config_path):
                if fn.endswith(".json"):
                    with open(os.path.join(config_path, fn)) as f:
                        cfg = json.load(f)
                        key = cfg.get("inferenceGatewayApiKey", "")
                        if key:
                            return key
    except Exception:
        pass

    return ""


def fetch_balance():
    key = _load_api_key()
    if not key:
        # Keep last known balance if we previously had one
        with bal_state.lock:
            if not bal_state.balance.startswith("¥"):
                bal_state.balance = "(未找到 API Key)"
        return

    try:
        r = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10)
        if r.status_code == 200:
            data = r.json()
            infos = data.get("balance_infos", [])
            if infos:
                info = infos[0]
                total = info.get("total_balance", "?")
                granted = info.get("granted_balance", "0")
                topped = info.get("topped_up_balance", "0")
                with bal_state.lock:
                    bal_state.balance = f"¥{total} (充值¥{topped} + 赠送¥{granted})"
            else:
                with bal_state.lock:
                    bal_state.balance = f"¥? ({json.dumps(data)[:80]})"
        else:
            # Keep last known balance on HTTP error
            pass
    except Exception:
        # Keep last known balance on network error
        pass


# ── Dashboard HTTP Server ────────────────────────────────
DASHBOARD = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DeepSeek Monitor</title>
<style>:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--muted:#8b949e;--green:#3fb950;--blue:#58a6ff;--orange:#d2991d}*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px;max-width:900px;margin:0 auto}h1{font-size:20px;margin-bottom:24px;color:var(--blue)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}.card .label{font-size:12px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}.card .value{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}.card .sub{font-size:12px;color:var(--muted);margin-top:4px}.value.green{color:var(--green)}.value.orange{color:var(--orange)}table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden}th{text-align:left;padding:10px 16px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}td{padding:8px 16px;font-size:13px;font-variant-numeric:tabular-nums;border-bottom:1px solid var(--border)}tr:last-child td{border-bottom:none}.bar{margin-top:24px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:8px;font-size:12px;color:var(--muted);text-align:center}.bar span{color:var(--green)}.section-title{font-size:13px;color:var(--muted);margin:24px 0 8px;text-transform:uppercase;letter-spacing:.5px}.model-tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;background:var(--border)}</style></head><body>
<h1>DeepSeek Token 消耗</h1>
<div class="grid"><div class="card"><div class="label">今日请求</div><div class="value green" id="treq">-</div></div><div class="card"><div class="label">今日 Tokens</div><div class="value green" id="ttot">-</div><div class="sub">输入 <span id="tpr">-</span> · 输出 <span id="tco">-</span></div></div><div class="card"><div class="label">今日费用</div><div class="value orange" id="tcost">-</div></div><div class="card"><div class="label">本月 Tokens</div><div class="value" id="mtot">-</div><div class="sub">费用 ~<span id="mcost">-</span></div></div></div>
<div class="section-title">最近请求</div>
<table><thead><tr><th>时间</th><th>模型</th><th>输入</th><th>输出</th><th>合计</th></tr></thead><tbody id="hist"><tr><td colspan="5" style="text-align:center;color:var(--muted)">加载中...</td></tr></tbody></table>
<div class="bar">JSONL 监视运行中 · <span id="uptime">0s</span></div>
<script>const f=n=>n!=null?n.toLocaleString():'-';const c=n=>'¥'+(n??0).toFixed(2);
async function R(){try{const r=await fetch('/stats');const d=await r.json();
document.getElementById('treq').textContent=f(d.today.requests);
document.getElementById('ttot').textContent=f(d.today.total);
document.getElementById('tpr').textContent=f(d.today.prompt);
document.getElementById('tco').textContent=f(d.today.completion);
document.getElementById('tcost').textContent=c(d.today.cost);
document.getElementById('mtot').textContent=f(d.month.total);
document.getElementById('mcost').textContent=c(d.month.cost);
document.getElementById('hist').innerHTML=d.recent.map(r=>`<tr><td>${r.ts?.slice(11,19)||'-'}</td><td><span class="model-tag">${r.model||'-'}</span></td><td>${f(r.prompt)}</td><td>${f(r.completion)}</td><td>${f(r.total)}</td></tr>`).join('')||'<tr><td colspan="5" style="text-align:center;color:var(--muted)">暂无数据</td></tr>'}catch(e){console.error(e)}
let S=Date.now();setInterval(()=>{document.getElementById('uptime').textContent=Math.floor((Date.now()-S)/1000)+'s'},1000);R();setInterval(R,10000);</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress logs

    def do_GET(self):
        if self.path == "/":
            self._html(200, DASHBOARD)
        elif self.path == "/stats":
            self._json(200, get_stats())
        else:
            self._json(404, {"error": "not found"})

    def _html(self, code, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_dashboard():
    server = HTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"  Dashboard: http://localhost:{PORT}")
    server.serve_forever()


# ── Menu Bar (rumps) ────────────────────────────────────
class DeepSeekBar(rumps.App):
    def __init__(self):
        super().__init__("DS", title="DS ¥--", quit_button=None)
        self._req_item = rumps.MenuItem("今日请求: --")
        self._tok_item = rumps.MenuItem("今日 Token: --")
        self._cost_item = rumps.MenuItem("今日费用: ¥--")
        self._month_item = rumps.MenuItem("本月费用: ¥--")
        self._bal_item = rumps.MenuItem("余额: --")

        self.menu.add(self._req_item)
        self.menu.add(self._tok_item)
        self.menu.add(self._cost_item)
        self.menu.add(rumps.separator)
        self.menu.add(self._month_item)
        self.menu.add(self._bal_item)
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🌐 打开仪表盘", callback=self._open_dashboard))
        self.menu.add(rumps.MenuItem("🔄 刷新余额", callback=lambda _: threading.Thread(target=fetch_balance, daemon=True).start()))
        self.menu.add(rumps.MenuItem("💎 DeepSeek 充值", callback=lambda _: webbrowser.open("https://platform.deepseek.com/top_up")))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("退出", callback=lambda _: rumps.quit_application()))

    def _open_dashboard(self, _):
        webbrowser.open(f"http://localhost:{PORT}")

    @rumps.timer(5)
    def _tick(self, _):
        try:
            # Tail JSONL for new data
            tail_jsonl()

            s = get_stats()
            t = s["today"]
            cost = t["cost"]
            mc = s["month"]["cost"]

            bal = ""
            with bal_state.lock:
                bal = bal_state.balance

            # Parse balance number: "¥100.00 (充值¥90 + 赠送¥10)" -> "100.00"
            bal_short = ""
            if bal.startswith("¥"):
                # Extract just the first number
                parts = bal[1:].split()
                if parts:
                    bal_short = parts[0]

            # Menu bar title: cost + balance
            if bal_short:
                self.title = f"DS ¥{cost:.2f} | ¥{bal_short}"
            else:
                self.title = f"DS ¥{cost:.4f}" if cost > 0 else "DS ¥0"

            self._req_item.title = f"今日请求: {t['requests']} 次"
            self._tok_item.title = f"今日 Token: {t['total']:,}  (入 {t['prompt']:,} / 出 {t['completion']:,})"
            self._cost_item.title = f"今日费用: ¥{cost:.4f}"
            self._month_item.title = f"本月费用: ¥{mc:.4f}  | 本月 Token: {s['month']['total']:,}"
            self._bal_item.title = f"余额: {bal}"
        except Exception:
            pass


# ── Main ─────────────────────────────────────────────────
def main():
    init_db()

    # Start dashboard server in background thread
    threading.Thread(target=run_dashboard, daemon=True).start()
    time.sleep(0.5)

    # Initial balance check
    threading.Thread(target=fetch_balance, daemon=True).start()

    # Periodic balance refresh
    def balance_loop():
        while True:
            time.sleep(BALANCE_INTERVAL)
            fetch_balance()

    threading.Thread(target=balance_loop, daemon=True).start()

    print("\n  DeepSeek Monitor — 菜单栏 (零侵入)")
    print(f"  仪表盘: http://localhost:{PORT}")
    print(f"  数据库: {DB_PATH}")
    print(f"  方式:   尾随 JSONL 文件 (不改任何 Claude 配置)\n")

    DeepSeekBar().run()


if __name__ == "__main__":
    main()
