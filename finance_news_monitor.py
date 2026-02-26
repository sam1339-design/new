#!/usr/bin/env python3
"""
24小时财经新闻监控脚本：
- 定时抓取 RSS 新闻源
- 去重后自动在终端打印新消息
- 可选桌面通知（需安装 plyer）
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable, Set


def try_notify(title: str, message: str) -> None:
    """尝试发送桌面通知，失败时静默。"""
    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass


def read_text(node: ET.Element | None, default: str = "") -> str:
    if node is None or node.text is None:
        return default
    return node.text.strip()


def parse_rss(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        content = resp.read()

    root = ET.fromstring(content)
    items: list[dict] = []

    # 兼容 RSS2.0: channel/item
    for item in root.findall("./channel/item"):
        title = read_text(item.find("title"), "(无标题)")
        link = read_text(item.find("link"))
        published = read_text(item.find("pubDate"))
        guid = read_text(item.find("guid"))
        items.append(
            {
                "id": guid or link or f"{title}-{published}",
                "title": title,
                "link": link,
                "published": published,
                "source": url,
            }
        )

    return items


def fetch_news(urls: Iterable[str], seen_ids: Set[str]) -> list[dict]:
    """拉取新闻并返回未出现过的新条目。"""
    fresh_items: list[dict] = []

    for url in urls:
        try:
            entries = parse_rss(url)
        except Exception as exc:
            now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] 来源抓取失败: {url} ({exc})")
            continue

        for entry in entries:
            entry_id = entry["id"]
            if not entry_id or entry_id in seen_ids:
                continue

            seen_ids.add(entry_id)
            fresh_items.append(entry)

    return fresh_items


def monitor_news(urls: list[str], interval_sec: int, run_hours: int) -> None:
    """按设定时长循环拉取新闻。"""
    start_time = dt.datetime.now()
    end_time = start_time + dt.timedelta(hours=run_hours)
    seen_ids: Set[str] = set()

    print(f"开始监控财经新闻，开始时间: {start_time:%Y-%m-%d %H:%M:%S}")
    print(f"结束时间: {end_time:%Y-%m-%d %H:%M:%S}")
    print(f"轮询间隔: {interval_sec} 秒")
    print("-" * 60)

    while dt.datetime.now() < end_time:
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            new_items = fetch_news(urls, seen_ids)
            if new_items:
                for item in new_items:
                    msg = (
                        f"[{now}] 新财经消息\n"
                        f"标题: {item['title']}\n"
                        f"时间: {item['published']}\n"
                        f"链接: {item['link']}\n"
                    )
                    print(msg)
                    try_notify("新财经消息", item["title"])
            else:
                print(f"[{now}] 暂无新消息")
        except Exception as exc:
            print(f"[{now}] 抓取失败: {exc}")

        time.sleep(interval_sec)

    print("监控结束。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="24小时财经新闻自动监控")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="轮询间隔（秒），默认 60",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="运行时长（小时），默认 24",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="自定义 RSS 地址，可传多次",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    default_sources = [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    ]
    sources = args.source or default_sources

    monitor_news(sources, args.interval, args.hours)


if __name__ == "__main__":
    main()
