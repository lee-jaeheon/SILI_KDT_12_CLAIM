import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "database", "claims.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # dict처럼 접근 가능
    return conn
