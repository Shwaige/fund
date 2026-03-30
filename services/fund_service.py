import json
import re
from datetime import datetime

import pandas as pd
import requests


API_BASE = "https://jeokegeywtms.sealosbja.site/api"
REALTIME_TIMEOUT = 5
HISTORY_TIMEOUT = 3


def parse_holdings(raw_text, username):
    valid_data = []
    invalid_lines = []
    for line_no, line in enumerate(raw_text.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [part for part in re.split(r'[，,\t ]+', line) if part]
        if len(parts) < 3:
            invalid_lines.append(line_no)
            continue
        try:
            shares = float(re.sub(r'[^-0-9.]', '', parts[2]))
        except ValueError:
            invalid_lines.append(line_no)
            continue
        cost_basis = None
        if len(parts) >= 4:
            try:
                cost_basis = float(re.sub(r'[^-0-9.]', '', parts[3]))
            except ValueError:
                invalid_lines.append(line_no)
                continue
        valid_data.append((username, parts[0], parts[1], shares, cost_basis))
    return valid_data, invalid_lines


def fetch_fund_snapshot(session, fund_code, today_s):
    curr_v, prev_v, zzl, tag = None, None, 0.0, "估值"

    rt_res = session.get(f"{API_BASE}/fund-realtime/{fund_code}.js", timeout=REALTIME_TIMEOUT)
    rt_res.raise_for_status()
    rt_match = re.search(r'jsonpgz\((.*)\)', rt_res.text)
    if not rt_match:
        raise ValueError(f"{fund_code} 实时接口返回格式异常")

    rt_data = json.loads(rt_match.group(1))
    prev_v = float(rt_data['dwjz'])
    curr_v = float(rt_data['gsz'])
    zzl = float(rt_data['gszzl'])

    hist_res = session.get(
        f"{API_BASE}/fund-nav-history",
        params={
            "fundCode": fund_code,
            "pageIndex": 1,
            "pageSize": 1,
            "startDate": today_s,
            "endDate": today_s,
        },
        timeout=HISTORY_TIMEOUT,
    )
    hist_res.raise_for_status()
    h_res = hist_res.json()
    if h_res.get("Data") and h_res["Data"].get("LSJZList"):
        item = h_res["Data"]["LSJZList"][0]
        if item.get("FSRQ") == today_s:
            curr_v = float(item["DWJZ"])
            zzl = float(item.get("JZZZL", zzl))
            tag = "今日已更新"

    return curr_v, prev_v, zzl, tag


def build_dashboard_data(df):
    total_cur, total_yest, total_cost, temp_results = 0.0, 0.0, 0.0, []
    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    failed_funds = []
    missing_cost_funds = []
    session = requests.Session()

    for _, row in df.iterrows():
        try:
            shares = float(row['shares'])
            fund_code = row['code']
            cost_basis = float(row['cost_basis']) if pd.notna(row.get('cost_basis')) else None
            curr_v, prev_v, zzl, tag = fetch_fund_snapshot(session, fund_code, today_s)

            if curr_v is None or prev_v is None:
                continue

            cv = shares * curr_v
            yv = shares * prev_v
            single_profit = cv - yv
            cumulative_profit = None if cost_basis is None else cv - cost_basis
            cumulative_pct = None if cost_basis in (None, 0) else round((cumulative_profit / cost_basis) * 100, 2)

            total_cur += cv
            total_yest += yv
            if cost_basis is not None:
                total_cost += cost_basis
            else:
                missing_cost_funds.append(f"{row['name']}({row['code']})")

            temp_results.append({
                '基金名称': row['name'],
                '代码': fund_code,
                '持有份额': shares,
                '买入总金额': cost_basis,
                '今日市值': cv,
                '昨日市值': yv,
                '当日盈亏': single_profit,
                '累计盈亏': cumulative_profit,
                '累计收益率(%)': cumulative_pct,
                '今日涨幅(%)': zzl,
                '状态': tag,
            })
        except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as exc:
            failed_funds.append(f"{row['name']}({row['code']}): {exc}")

    profit_sum = total_cur - total_yest
    pct = round((profit_sum / total_yest * 100), 2) if total_yest != 0 else 0.0
    cumulative_profit_sum = total_cur - total_cost if total_cost != 0 else 0.0
    cumulative_pct_sum = round((cumulative_profit_sum / total_cost) * 100, 2) if total_cost != 0 else 0.0

    return {
        "now": now,
        "today_s": today_s,
        "failed_funds": failed_funds,
        "missing_cost_funds": missing_cost_funds,
        "total_cur": total_cur,
        "total_yest": total_yest,
        "total_cost": total_cost,
        "profit_sum": profit_sum,
        "pct": pct,
        "cumulative_profit_sum": cumulative_profit_sum,
        "cumulative_pct_sum": cumulative_pct_sum,
        "positions": temp_results,
    }
