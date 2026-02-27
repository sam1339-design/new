# 每日复盘生成器（东方财富）

这个脚本会抓取东方财富涨停池数据，并输出可直接发到群里的每日复盘 Markdown，包含：

- 个股涨停时间（首次封板时间、最后封板时间）
- 个股涨停原因（通过东方财富诊股接口文字解读补充）

## 用法

```bash
python daily_review_eastmoney.py --date 20260227 --top 20 --output review_20260227.md
```

参数说明：

- `--date`: 交易日，格式 `YYYYMMDD`（默认今天）
- `--top`: 输出前 N 只涨停股，传 `0` 输出全量
- `--output`: 输出文件路径；不填则打印到终端

## 示例

```bash
python daily_review_eastmoney.py --date 20260227 --top 5
```

