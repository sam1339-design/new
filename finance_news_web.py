#!/usr/bin/env python3
"""本地财经新闻网页监控：启动后访问 http://127.0.0.1:8000 查看自动刷新新闻。"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass
class NewsItem:
    id: str
    title: str
    link: str
    published: str
    source: str
    seen_at: str


def read_text(node: ET.Element | None, default: str = "") -> str:
    if node is None or node.text is None:
        return default
    return node.text.strip()


def parse_rss(url: str) -> list[NewsItem]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CodexNewsBot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()

    root = ET.fromstring(content)
    items: list[NewsItem] = []

    for item in root.findall("./channel/item"):
        title = read_text(item.find("title"), "(无标题)")
        link = read_text(item.find("link"))
        published = read_text(item.find("pubDate"))
        guid = read_text(item.find("guid"))
        item_id = guid or link or f"{title}-{published}"
        items.append(
            NewsItem(
                id=item_id,
                title=title,
                link=link,
                published=published,
                source=url,
                seen_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

    return items


class NewsStore:
    def __init__(self, sources: list[str], poll_seconds: int, max_items: int = 100) -> None:
        self.sources = sources
        self.poll_seconds = poll_seconds
        self.max_items = max_items
        self._seen_ids: set[str] = set()
        self._items: list[NewsItem] = []
        self._lock = threading.Lock()
        self._last_error = ""

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "items": [asdict(x) for x in self._items],
                "count": len(self._items),
                "last_error": self._last_error,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def poll_once(self) -> None:
        fresh: list[NewsItem] = []
        errors: list[str] = []
        for url in self.sources:
            try:
                for item in parse_rss(url):
                    if not item.id or item.id in self._seen_ids:
                        continue
                    self._seen_ids.add(item.id)
                    fresh.append(item)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")

        with self._lock:
            self._last_error = " | ".join(errors)
            if fresh:
                self._items = (fresh + self._items)[: self.max_items]

    def run_forever(self) -> None:
        while True:
            try:
                self.poll_once()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._last_error = str(exc)
            time.sleep(self.poll_seconds)


HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>财经新闻监控面板</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 24px; background: #f7f9fc; color: #222; }
    h1 { margin: 0 0 6px 0; }
    .meta { color: #666; margin-bottom: 16px; }
    .err { color: #b00020; font-weight: 600; }
    .item { background: #fff; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .item a { color: #0b5ed7; text-decoration: none; }
    .small { font-size: 12px; color: #666; margin-top: 6px; }
  </style>
</head>
<body>
  <h1>📈 财经新闻实时监控</h1>
  <div class="meta">页面每 10 秒自动刷新一次</div>
  <div id="status" class="meta">初始化中（请等待首次抓取）...</div>
  <div id="error" class="err"></div>
  <div id="list"></div>

  <script>
    async function loadNews() {
      try {
        const res = await fetch('/news');
        const data = await res.json();
        document.getElementById('status').textContent = `已收集 ${data.count} 条，更新时间：${data.updated_at}`;
        document.getElementById('error').textContent = data.last_error ? `抓取异常：${data.last_error}` : '';

        const list = document.getElementById('list');
        list.innerHTML = '';

        if (!data.items.length) {
          const hint = data.last_error ? '暂时没有可显示的数据，请检查 RSS 源或网络。' : '暂时还没有新闻，请稍候...';
          list.innerHTML = `<div class="item">${hint}</div>`;
          return;
        }

        for (const item of data.items.slice(0, 20)) {
          const div = document.createElement('div');
          div.className = 'item';
          div.innerHTML = `
            <div><a href="${item.link}" target="_blank" rel="noreferrer noopener">${item.title}</a></div>
            <div class="small">发布时间：${item.published || '-'} ｜ 抓取时间：${item.seen_at}</div>
          `;
          list.appendChild(div);
        }
      } catch (e) {
        document.getElementById('error').textContent = `页面请求失败：${e}`;
      }
    }

    loadNews();
    setInterval(loadNews, 10000);
  </script>
</body>
</html>
"""


def build_handler(store: NewsStore):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path in ("/news", "/api/news"):
                payload = json.dumps(store.snapshot(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            # 在预览环境中路径可能不是根路径，这里统一回退到首页，避免出现 Not Found。
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="财经新闻网页监控")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=int, default=30, help="抓取间隔（秒）")
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args()

    sources = args.source or [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    ]

    store = NewsStore(sources=sources, poll_seconds=args.interval)
    store.poll_once()

    worker = threading.Thread(target=store.run_forever, daemon=True)
    worker.start()

    server = ThreadingHTTPServer((args.host, args.port), build_handler(store))
    print(f"服务已启动：http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
