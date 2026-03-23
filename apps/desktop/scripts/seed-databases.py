"""构建时预生成 demo.db 和 querygpt.db，打包进桌面版。

运行时只需复制到用户目录即可，零初始化。
"""

import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

# 让 import app.* 能找到
API_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "api")
sys.path.insert(0, API_DIR)

DATA_DIR = os.path.join(API_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def build_demo_db():
    """生成 demo.db（示例销售数据库）"""
    demo_path = os.path.join(DATA_DIR, "demo.db")
    if os.path.exists(demo_path):
        os.remove(demo_path)

    # DATA_DIR env 让 demo_db 模块把文件写到正确位置
    os.environ["DATA_DIR"] = DATA_DIR
    from app.core.demo_db import init_demo_database

    path = init_demo_database()
    print(f"  demo.db created: {path}")
    return demo_path


def build_querygpt_db(demo_db_path: str):
    """生成预填充的 querygpt.db（连接 + 术语 + AppSettings）"""
    import sqlite3

    db_path = os.path.join(DATA_DIR, "querygpt.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()

    # 建表（与 SQLAlchemy 模型对应）
    c.execute("""CREATE TABLE connections (
        id CHAR(32) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        driver VARCHAR(20) NOT NULL,
        host VARCHAR(255),
        port INTEGER,
        username VARCHAR(100),
        password_encrypted TEXT,
        database_name VARCHAR(100),
        extra_options JSON DEFAULT '{}',
        is_default BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE models (
        id CHAR(32) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        provider VARCHAR(50) NOT NULL,
        model_id VARCHAR(100) NOT NULL,
        base_url VARCHAR(500),
        api_key_encrypted TEXT,
        extra_options JSON DEFAULT '{}',
        is_default BOOLEAN DEFAULT 0,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE conversations (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) REFERENCES connections(id) ON DELETE SET NULL,
        model_id CHAR(32) REFERENCES models(id) ON DELETE SET NULL,
        title VARCHAR(200),
        status VARCHAR(20) DEFAULT 'active',
        is_favorite BOOLEAN DEFAULT 0,
        extra_data JSON DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX idx_conversations_status ON conversations(status)")

    c.execute("""CREATE TABLE messages (
        id CHAR(32) PRIMARY KEY,
        conversation_id CHAR(32) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        extra_data JSON DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX idx_messages_conversation ON messages(conversation_id)")

    c.execute("""CREATE TABLE app_settings (
        id INTEGER PRIMARY KEY,
        default_model_id CHAR(32) REFERENCES models(id) ON DELETE SET NULL,
        default_connection_id CHAR(32) REFERENCES connections(id) ON DELETE SET NULL,
        context_rounds INTEGER DEFAULT 5,
        python_enabled BOOLEAN DEFAULT 1,
        diagnostics_enabled BOOLEAN DEFAULT 1,
        auto_repair_enabled BOOLEAN DEFAULT 1,
        demo_initialized BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE semantic_terms (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) REFERENCES connections(id) ON DELETE CASCADE,
        term VARCHAR(100) NOT NULL,
        expression TEXT NOT NULL,
        term_type VARCHAR(20) DEFAULT 'metric',
        description TEXT,
        examples JSON DEFAULT '[]',
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX idx_semantic_terms_term ON semantic_terms(term)")

    c.execute("""CREATE TABLE table_relationships (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
        source_table VARCHAR(100) NOT NULL,
        source_column VARCHAR(100) NOT NULL,
        target_table VARCHAR(100) NOT NULL,
        target_column VARCHAR(100) NOT NULL,
        relationship_type VARCHAR(10) DEFAULT '1:N',
        join_type VARCHAR(20) DEFAULT 'LEFT',
        description TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE prompts (
        id CHAR(32) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        content TEXT NOT NULL,
        description TEXT,
        version INTEGER DEFAULT 1,
        is_active BOOLEAN DEFAULT 1,
        is_default BOOLEAN DEFAULT 0,
        parent_id CHAR(32) REFERENCES prompts(id) ON DELETE SET NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    # 插入 demo connection — database_name 用占位符，运行时替换
    conn_id = uuid4().hex
    c.execute(
        "INSERT INTO connections (id, name, driver, database_name, extra_options, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (conn_id, "Sample Database", "sqlite", "__DEMO_DB_PATH__", "{}", 1, now, now),
    )

    # 插入 demo semantic terms
    terms = [
        {
            "term": "GMV",
            "expression": "SUM(sales.quantity * sales.unit_price)",
            "term_type": "metric",
            "description": "Gross Merchandise Value — total sales revenue (quantity × unit price)",
            "examples": ["What is this month's GMV?", "GMV by region"],
        },
        {
            "term": "Top Customers",
            "expression": "customers.id IN (SELECT customer_id FROM sales GROUP BY customer_id HAVING SUM(amount) > 100000)",
            "term_type": "filter",
            "description": "Customers with cumulative spending over 100,000",
            "examples": ["List all top customers", "Top customers by region"],
        },
        {
            "term": "Average Order Value",
            "expression": "AVG(sales.amount)",
            "term_type": "metric",
            "description": "Average transaction amount per sale",
            "examples": ["What is the average order value?", "AOV trend over the past 6 months"],
        },
    ]
    for t in terms:
        c.execute(
            "INSERT INTO semantic_terms (id, connection_id, term, expression, term_type, description, examples, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid4().hex, conn_id, t["term"], t["expression"], t["term_type"], t["description"], json.dumps(t["examples"]), 1, now, now),
        )

    # 插入 AppSettings（demo_initialized=True）
    c.execute(
        "INSERT INTO app_settings (id, default_connection_id, context_rounds, python_enabled, diagnostics_enabled, auto_repair_enabled, demo_initialized, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, conn_id, 5, 1, 1, 1, 1, now, now),
    )

    conn.commit()
    conn.close()
    print(f"  querygpt.db created: {db_path}")
    return db_path


if __name__ == "__main__":
    print("=== Seeding databases for desktop build ===")
    demo_path = build_demo_db()
    build_querygpt_db(demo_path)
    print("Done.")
