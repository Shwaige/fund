import streamlit as st
import pandas as pd
import sqlite3
import requests
import json
import re
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import time


# 1. 兼容性刷新函数
def universal_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


# 2. 数据库初始化
def init_db():
    conn = sqlite3.connect('my_assets_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS holdings (username TEXT, name TEXT, code TEXT, shares REAL)')
    c.execute(
        'CREATE TABLE IF NOT EXISTS daily_history (username TEXT, record_date TEXT, total_value REAL, base_value REAL)')
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?,?)", ("admin", "123456"))
    conn.commit()
    return conn


conn = init_db()
st.set_page_config(page_title="资产管家", layout="wide")

# 强制修正颜色习惯 (红涨绿跌)
st.markdown("""
    <style>
    [data-testid="stMetricDelta"] svg { fill: currentColor !important; }
    [data-testid="stMetricDelta"] > div:nth-child(2) { color: #ff4b4b !important; } 
    [data-testid="stMetricDelta"] { color: #ff4b4b !important; }
    </style>
""", unsafe_allow_html=True)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# --- 侧边栏 ---
with st.sidebar:
    st.title("🔐 同步中心")
    u_in = st.text_input("用户名", value="admin")
    p_in = st.text_input("密码", type="password", value="123456")
    if st.button("进入系统/更新数据"):
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE username=?", (u_in,))
        row = c.fetchone()
        if row and row[0] == p_in:
            st.session_state.logged_in = True
            st.session_state.user = u_in
            universal_rerun()
        else:
            st.error("密码错误")

if not st.session_state.logged_in:
    st.info("👋 请在左侧登录")
    st.stop()

# --- 主界面 ---
st.title("📊 实盘看板")

with st.expander("📝 编辑持仓"):
    raw_text = st.text_area("格式：名称,代码,份额", height=150, placeholder="可以直接粘贴你的持仓列表...")
    if st.button("保存更新"):
        lines = raw_text.strip().split('\n')
        valid_data = []
        for line in lines:
            parts = re.split(r'[，, \t]', line.strip())
            if len(parts) >= 3:
                try:
                    name = parts[0]
                    code = parts[1]
                    shares = float(re.sub(r'[^-0-9.]', '', parts[2]))
                    valid_data.append((st.session_state.user, name, code, shares))
                except:
                    continue
        if valid_data:
            c = conn.cursor()
            c.execute("DELETE FROM holdings WHERE username=?", (st.session_state.user,))
            c.executemany("INSERT INTO holdings VALUES (?,?,?,?)", valid_data)
            conn.commit()
            universal_rerun()

# --- 核心计算逻辑 ---
df = pd.read_sql_query("SELECT * FROM holdings WHERE username=?", conn, params=(st.session_state.user,))

if not df.empty:
    total_cur, total_yest, temp_results = 0.0, 0.0, []
    now = datetime.now()
    today_s = now.strftime("%Y-%m-%d")
    current_ts = int(time.time() * 1000)

    with st.spinner('正在同步行情与市值...'):
        for _, row in df.iterrows():
            try:
                shares = float(row['shares'])
                f_code = row['code']
                curr_v, prev_v, zzl, tag = None, None, 0.0, "估值"

                # 1. 先拿实时接口的数据 (作为保底和获取昨日净值基准)
                rt_res = requests.get(f"https://jeokegeywtms.sealosbja.site/api/fund-realtime/{f_code}.js", timeout=5)
                rt_match = re.search(r'jsonpgz\((.*)\)', rt_res.text)
                if rt_match:
                    rt_data = json.loads(rt_match.group(1))
                    # 关键：昨日净值直接用实时接口里的 dwjz，这是最准确的昨日定盘价
                    prev_v = float(rt_data['dwjz'])
                    # 先预设今日净值为估值
                    curr_v = float(rt_data['gsz'])
                    zzl = float(rt_data['gszzl'])

                # 2. 尝试用历史接口校准今日数据 (如果今日已更新，则覆盖估值)
                try:
                    # 严格使用你提供的历史接口格式
                    hist_url = f"https://jeokegeywtms.sealosbja.site/api/fund-nav-history?fundCode={f_code}&pageIndex=1&pageSize=1&startDate={today_s}&endDate={today_s}"
                    h_res = requests.get(hist_url, timeout=3).json()
                    if h_res.get("Data") and h_res["Data"].get("LSJZList"):
                        item = h_res["Data"]["LSJZList"][0]
                        if item.get("FSRQ") == today_s:
                            curr_v = float(item["DWJZ"])  # 用官方确认为准
                            zzl = float(item.get("JZZZL", zzl))
                            tag = "今日已更新"
                except:
                    pass  # 历史接口若报错或无数据，维持“估值”状态

                # 3. 纯金额对撞计算
                if curr_v is not None and prev_v is not None:
                    cv = shares * curr_v  # 今日市值
                    yv = shares * prev_v  # 昨日市值 (昨日持有规模)
                    single_profit = cv - yv  # 盈亏金额

                    total_cur += cv
                    total_yest += yv

                    temp_results.append({
                        '基金名称': row['name'],
                        '代码': f_code,
                        '持有份额': shares,
                        '今日市值': cv,
                        '昨日市值': yv,
                        '当日盈亏': single_profit,
                        '今日涨幅(%)': zzl,
                        '状态': tag
                    })
            except:
                continue
    # 1. 顶部指标
    profit_sum = total_cur - total_yest
    pct = round((profit_sum / total_yest * 100), 2) if total_yest != 0 else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("当前总市值", f"¥{total_cur:,.2f}")
    c2.metric("昨日持有规模", f"¥{total_yest:,.2f}")
    c3.metric("今日盈亏", f"¥{profit_sum:,.2f}", f"{'+' if pct > 0 else ''}{pct}%")
    c4.metric("同步时间", now.strftime("%H:%M:%S"))

    # 2. 资产明细表格 (排序与渲染)
    st.markdown("### 📋 资产明细 (已按盈亏排序)")
    display_df = pd.DataFrame(temp_results)

    if not display_df.empty:
        # 排序：由于 temp_results 里已经有了“当日盈亏”这个 Key，这里不会报错
        display_df = display_df.sort_values(by="当日盈亏", ascending=False)


        def style_profit(val):
            color = '#ff4b4b' if val > 0 else '#00873c' if val < 0 else '#666'
            return f'color: {color}; font-weight: bold'


        styled_df = display_df.style.map(style_profit, subset=['今日涨幅(%)', '当日盈亏']) \
            .format({
            '持有份额': '{:,.2f}',
            '昨日市值': '¥{:,.2f}',
            '今日市值': '¥{:,.2f}',
            '今日涨幅(%)': '{:+.2f}%',
            '当日盈亏': '¥{:,.2f}'
        })

        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # 3. 历史记录自动保存
    db_cur = conn.cursor()
    db_cur.execute("DELETE FROM daily_history WHERE username=? AND record_date=?", (st.session_state.user, today_s))
    db_cur.execute("INSERT INTO daily_history VALUES (?,?,?,?)",
                   (st.session_state.user, today_s, total_cur, total_yest))
    conn.commit()

    # --- 历史记录显示 ---
    st.markdown("---")
    st.markdown("### 📅 历史收益明细")
    h_df = pd.read_sql_query(
        "SELECT record_date, total_value, base_value FROM daily_history WHERE username=? ORDER BY record_date DESC",
        conn, params=(st.session_state.user,))

    if not h_df.empty:
        h_rows = ""
        for _, r in h_df.iterrows():
            amt = r['total_value'] - r['base_value']
            val = round(((r['total_value'] / r['base_value'] - 1) * 100), 2) if r['base_value'] != 0 else 0
            icon = "🔴" if val > 0 else "🟢" if val < 0 else "➖"
            color = "#ff4b4b" if val > 0 else "#00873c" if val < 0 else "#666"
            h_rows += f"<tr><td>{r['record_date']}</td><td style='color:{color}; font-weight:bold;'>¥{amt:,.2f}</td><td style='color:{color};'>{icon} {val}%</td></tr>"

        history_html = f"<style>.h-table{{width:100%; border-collapse:collapse; font-family:sans-serif; text-align:center;}}.h-table th{{padding:12px; background:#f8f9fa; color:#666; font-size:13px; border-bottom:2px solid #eee;}}.h-table td{{padding:12px; border-bottom:1px solid #eee; font-size:14px;}}</style><table class='h-table'><tr><th>日期</th><th>盈亏金额</th><th>收益率</th></tr>{h_rows}</table>"
        components.html(history_html, height=(len(h_df) * 50) + 60)
else:
    st.info("💡 请先录入持仓数据")