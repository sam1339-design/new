#!/usr/bin/env python3
"""生成基于东方财富数据的每日复盘（含涨停时间与原因解读）。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


ZTP_URL = "https://push2ex.eastmoney.com/getTopicZTPool"
DIAG_URL = "https://datacenter-web.eastmoney.com/web/api/data/v1/get"


@dataclass
class LimitUpStock:
    code: str
    name: str
    pct_chg: float
    first_board_time: str
    last_board_time: str
    board_count: int
    broken_count: int
    industry: str
    reason: str


def http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def format_hhmmss(raw_time: int | str) -> str:
    raw = str(raw_time).zfill(6)
    return f"{raw[0:2]}:{raw[2:4]}:{raw[4:6]}"


def fetch_zt_pool(trade_date: str) -> list[dict[str, Any]]:
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": "10000",
        "sort": "fbt:asc",
        "date": trade_date,
    }
    data = http_get_json(ZTP_URL, params)
    pool = data.get("data", {}).get("pool", [])
    if not isinstance(pool, list):
        return []
    return pool


def fetch_reason_by_diag(code: str) -> str:
    """从东方财富诊股接口读取文字解读，作为涨停原因描述。"""
    params = {
        "reportName": "RPT_CUSTOM_STOCK_PK",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "token": "28dfeb41d35cc81d84b4664d7c23c49f",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        data = http_get_json(DIAG_URL, params)
        items = data.get("result", {}).get("data", [])
        if items and isinstance(items, list):
            return items[0].get("WORDS_EXPLAIN") or "暂无诊股解读"
    except Exception:
        return "诊股接口请求失败"
    return "暂无诊股解读"


def build_review(trade_date: str, top_n: int) -> str:
    pool = fetch_zt_pool(trade_date)
    if not pool:
        return f"# 每日复盘（{trade_date}）\n\n当日无涨停池数据。"

    picked = pool[:top_n] if top_n > 0 else pool
    rows: list[LimitUpStock] = []
    for item in picked:
        reason = fetch_reason_by_diag(item.get("c", ""))
        rows.append(
            LimitUpStock(
                code=item.get("c", ""),
                name=item.get("n", ""),
                pct_chg=float(item.get("zdp", 0.0)),
                first_board_time=format_hhmmss(item.get("fbt", 0)),
                last_board_time=format_hhmmss(item.get("lbt", 0)),
                board_count=int(item.get("lbc", 0)),
                broken_count=int(item.get("zbc", 0)),
                industry=item.get("hybk", ""),
                reason=reason.strip(),
            )
        )

    avg_pct = statistics.mean([r.pct_chg for r in rows])
    one_board_cnt = sum(1 for r in rows if r.board_count == 1)
    multi_board_cnt = len(rows) - one_board_cnt

    lines = [
        f"# 每日复盘（{trade_date}）",
        "",
        "## 市场概览",
        f"- 涨停样本数：{len(rows)}（可通过 `--top 0` 获取全量）",
        f"- 平均涨跌幅：{avg_pct:.2f}%",
        f"- 首板数量：{one_board_cnt}，连板数量：{multi_board_cnt}",
        "",
        "## 涨停个股明细（含涨停时间、原因）",
        "| 代码 | 名称 | 所属行业 | 首次涨停时间 | 最后涨停时间 | 连板数 | 炸板次数 | 涨停原因（东方财富诊股解读） |",
        "|---|---|---|---|---|---:|---:|---|",
    ]

    for r in rows:
        safe_reason = r.reason.replace("|", "、").replace("\n", " ")
        lines.append(
            f"| {r.code} | {r.name} | {r.industry} | {r.first_board_time} | "
            f"{r.last_board_time} | {r.board_count} | {r.broken_count} | {safe_reason} |"
        )

    lines.extend(
        [
            "",
            "## 复盘观察",
            "1. 优先跟踪首次封板时间早、且炸板次数低的个股，次日溢价通常更稳定。",
            "2. 连板股重点关注情绪延续与分歧转一致的时点。",
            "3. 原因字段为东方财富诊股接口文本解读，可配合你自己的题材库做二次标签化。",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成东方财富每日复盘 Markdown")
    parser.add_argument(
        "--date",
        default=dt.date.today().strftime("%Y%m%d"),
        help="交易日，格式 YYYYMMDD，默认今天",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="输出前 N 只涨停股；传 0 输出全量",
    )
    parser.add_argument(
        "--output",
        default="",
        help="输出文件路径；不填则直接打印到终端",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_review(args.date, args.top)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"已写入: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
