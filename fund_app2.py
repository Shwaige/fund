import streamlit as st
import pandas as pd
import sqlite3
import requests
import json
import re
import streamlit.components.v1 as components
from datetime import datetime


# 1. 兼容性刷新
def universal_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


# 2. 数据库初始化 (增加自动创建管理员逻辑)
def init_db():
    conn = sqlite3.connect('my_assets_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS holdings (username TEXT, name TEXT, code TEXT, shares REAL)')
    c.execute(
        'CREATE TABLE IF NOT EXISTS daily_history (username TEXT, record_date TEXT, total_value REAL, base_value REAL)')

    # --- 新增：如果表里没用户，初始化一个 admin ---
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?,?)", ("admin", "123456"))
    # ------------------------------------------

    conn.commit()
    return conn

conn = init_db()
st.set_page_config(page_title="资产管家", layout="wide")

# 强制修正 Streamlit 默认的颜色习惯（通过注入 CSS 覆盖）
st.markdown("""
    <style>
    /* 让指标卡片正值为红色，负值为绿色 */
    [data-testid="stMetricDelta"] svg { fill: currentColor !important; }
    [data-testid="stMetricDelta"] > div:nth-child(2) { color: #ff4b4b !important; } /* 正值变红 */
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
    raw_text = st.text_area("格式：名称,代码,份额", height=80, placeholder="招商白酒,161725,1000")
    if st.button("保存更新"):
        lines = raw_text.strip().split('\n')
        valid_data = [(st.session_state.user, p[0], p[1], float(re.sub(r'[^-0-9.]', '', p[2])))
                      for line in lines if len(p := re.split(r'[，, \t]', line)) >= 3]
        if valid_data:
            c = conn.cursor()
            c.execute("DELETE FROM holdings WHERE username=?", (st.session_state.user,))
            c.executemany("INSERT INTO holdings VALUES (?,?,?,?)", valid_data)
            conn.commit()
            universal_rerun()

# --- 核心计算 ---
df = pd.read_sql_query("SELECT * FROM holdings WHERE username=?", conn, params=(st.session_state.user,))

if not df.empty:
    total_cur, total_yest, temp_results = 0.0, 0.0, []
    with st.spinner('同步行情中...'):
        for _, row in df.iterrows():
            try:
                res = requests.get(f"https://jeokegeywtms.sealosbja.site/api/fund-realtime/{row['code']}.js", timeout=5)
                data = json.loads(re.search(r'jsonpgz\((.*)\)', res.text).group(1))
                cv, yv = row['shares'] * float(data['gsz']), row['shares'] * float(data['dwjz'])
                total_cur += cv;
                total_yest += yv
                temp_results.append(
                    {'name': row['name'], 'code': row['code'], 'shares': row['shares'], 'cv': cv, 'yv': yv,
                     'zzl': data['gszzl']})
            except:
                continue

    # 1. 顶部指标 (delta_color="normal" 配合 CSS 修正颜色)
    profit = total_cur - total_yest
    pct = round((profit / total_yest * 100), 2) if total_yest != 0 else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("持有规模", f"¥{total_yest:,.2f}")
    # 这里我们显示带符号的盈亏，配合 CSS 强制渲染颜色
    c2.metric("今日预估盈亏", f"¥{profit:,.2f}", f"{'+' if pct > 0 else ''}{pct}%")
    c3.metric("最后同步", datetime.now().strftime("%H:%M:%S"))

    # 2. 持仓明细
    st.markdown("### 📋 资产明细")
    rows_detail = "".join([
                              f"<tr><td><b>{i['name']}</b><br><small style='color:#888'>{i['code']}</small></td><td>{i['shares']:,}</td><td>¥{i['yv']:,.2f}</td><td style='color:{'#ff4b4b' if float(i['zzl']) > 0 else '#00873c'};font-weight:bold;'>{'+' if float(i['zzl']) > 0 else ''}{i['zzl']}%</td><td style='color:{'#ff4b4b' if float(i['zzl']) > 0 else '#00873c'};font-weight:bold;'>¥{(i['cv'] - i['yv']):,.2f}</td></tr>"
                              for i in temp_results])
    components.html(
        f"<style>.f-table{{width:100%;border-collapse:collapse;font-family:sans-serif;text-align:left;}}.f-table th{{padding:12px;background:#f8f9fa;color:#666;font-size:13px;border-bottom:2px solid #eee;}}.f-table td{{padding:14px 12px;border-bottom:1px solid #eee;font-size:14px;}}</style><table class='f-table'><tr><th>名称/代码</th><th>份额</th><th>昨日市值</th><th>今日涨幅</th><th>预计收益</th></tr>{rows_detail}</table>",
        height=(len(temp_results) * 70) + 60)

    # 3. 历史记录
    today = datetime.now().strftime("%Y-%m-%d")
    db_cur = conn.cursor()
    db_cur.execute("DELETE FROM daily_history WHERE username=? AND record_date=?", (st.session_state.user, today))
    db_cur.execute("INSERT INTO daily_history VALUES (?,?,?,?)", (st.session_state.user, today, total_cur, total_yest))
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