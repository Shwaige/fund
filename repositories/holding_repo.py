import sqlite3

import pandas as pd


DB_PATH = "my_assets_v4.db"


def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS holdings (username TEXT, name TEXT, code TEXT, shares REAL, cost_basis REAL)')
    c.execute(
        'CREATE TABLE IF NOT EXISTS daily_history (username TEXT, record_date TEXT, total_value REAL, base_value REAL)'
    )
    c.execute("PRAGMA table_info(holdings)")
    holding_columns = {row[1] for row in c.fetchall()}
    if "cost_basis" not in holding_columns:
        c.execute("ALTER TABLE holdings ADD COLUMN cost_basis REAL")
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (?,?)", ("admin", "123456"))
    conn.commit()
    return conn


def authenticate_user(conn, username, password):
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone()
    return bool(row and row[0] == password)


def replace_holdings(conn, username, holdings):
    c = conn.cursor()
    c.execute("DELETE FROM holdings WHERE username=?", (username,))
    c.executemany(
        "INSERT INTO holdings (username, name, code, shares, cost_basis) VALUES (?,?,?,?,?)",
        holdings,
    )
    conn.commit()


def get_holdings_df(conn, username):
    return pd.read_sql_query("SELECT * FROM holdings WHERE username=?", conn, params=(username,))


def save_daily_history(conn, username, record_date, total_cur, total_yest):
    db_cur = conn.cursor()
    db_cur.execute("DELETE FROM daily_history WHERE username=? AND record_date=?", (username, record_date))
    db_cur.execute(
        "INSERT INTO daily_history VALUES (?,?,?,?)",
        (username, record_date, total_cur, total_yest),
    )
    conn.commit()


def get_daily_history_df(conn, username):
    return pd.read_sql_query(
        "SELECT record_date, total_value, base_value FROM daily_history WHERE username=? ORDER BY record_date DESC",
        conn,
        params=(username,),
    )
