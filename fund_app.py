import streamlit as st
import pandas as pd
import sqlite3
import requests
import json
import re
import streamlit.components.v1 as components
from datetime import datetime, timedelta


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
    yest_s = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    with st.spinner('正在同步行情...'):
        for _, row in df.iterrows():
            try:
                shares = float(row['shares'])
                f_code = row['code']

                # 获取实时/历史数据逻辑
                rt_res = requests.get(f"https://jeokegeywtms.sealosbja.site/api/fund-realtime/{f_code}.js", timeout=5)
                rt_data = json.loads(re.search(r'jsonpgz\((.*)\)', rt_res.text).group(1))
                curr_v = float(rt_data['gsz'])
                prev_v = float(rt_data['dwjz'])
                zzl = rt_data['gszzl']

                cv, yv = shares * curr_v, shares * prev_v
                single_profit = cv - yv
                total_cur += cv
                total_yest += yv
                temp_results.append({
                    '基金名称': row['name'], '代码': f_code, '持有份额': shares,
                    '昨日市值': yv, '今日市值': cv, '当日盈亏': single_profit, '今日涨幅(%)': float(zzl)
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

    # 2. 资产明细表格 (排序与拉伸优化)
    st.markdown("### 📋 资产明细 (点击表头可排序)")
    display_df = pd.DataFrame(temp_results).sort_values(by="当日盈亏", ascending=False)


    def style_profit(val):
        color = '#ff4b4b' if val > 0 else '#00873c' if val < 0 else '#666'
        return f'color: {color}; font-weight: bold'


    styled_df = display_df.style.map(style_profit, subset=['今日涨幅(%)', '当日盈亏']) \
        .format({'持有份额': '{:,.2f}', '昨日市值': '¥{:,.2f}', '今日市值': '¥{:,.2f}',
                 '今日涨幅(%)': '{:+.2f}%', '当日盈亏': '¥{:,.2f}'})

    # 兼容性布局处理
    try:
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    except:
        st.dataframe(styled_df, width=1200)  # 针对旧版 Mac 环境的降级处理

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