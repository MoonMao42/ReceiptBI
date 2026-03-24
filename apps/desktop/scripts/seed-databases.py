"""构建时预生成 demo.db 和 querygpt.db，打包进桌面版。

完全独立脚本，不导入任何 app 模块，避免触发 security/config 初始化。
运行时只需复制到用户目录即可，零初始化。
"""

import json
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "api", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── Demo data ──

PRODUCTS = [
    ("iPhone 15 Pro", "手机", 7999, 5500),
    ("iPhone 15", "手机", 5999, 4200),
    ("MacBook Pro 14", "电脑", 14999, 10500),
    ("MacBook Air", "电脑", 8999, 6300),
    ("iPad Pro", "平板", 6499, 4500),
    ("iPad Air", "平板", 4399, 3100),
    ("AirPods Pro", "配件", 1899, 1200),
    ("Apple Watch", "穿戴", 2999, 2100),
    ("Magic Keyboard", "配件", 999, 650),
    ("Studio Display", "显示器", 11499, 8000),
    ("Mac Mini", "电脑", 4499, 3100),
    ("HomePod", "智能家居", 2299, 1600),
]
REGIONS = ["华东", "华南", "华北", "西南", "华中"]
FIRST_NAMES = ["张", "李", "王", "刘", "陈", "杨", "黄", "赵", "周", "吴"]
LAST_NAMES = ["伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋", "勇", "艳", "杰", "涛", "明"]
ORDER_STATUSES = ["已完成", "已发货", "处理中", "已取消"]

DEMO_SEMANTIC_TERMS = [
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


def build_demo_db():
    """生成 demo.db（示例销售数据库）"""
    demo_path = os.path.join(DATA_DIR, "demo.db")
    if os.path.exists(demo_path):
        os.remove(demo_path)

    conn = sqlite3.connect(demo_path)
    c = conn.cursor()

    # 建表
    c.execute("""CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
        price REAL NOT NULL, cost REAL NOT NULL, created_at DATE DEFAULT CURRENT_DATE)""")
    c.execute("""CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, region TEXT NOT NULL,
        email TEXT, registered_at DATE NOT NULL)""")
    c.execute("""CREATE TABLE sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date DATE NOT NULL, product_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL,
        amount REAL NOT NULL, region TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id))""")
    c.execute("""CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT NOT NULL UNIQUE,
        order_date DATE NOT NULL, customer_id INTEGER NOT NULL, total_amount REAL NOT NULL,
        status TEXT NOT NULL, FOREIGN KEY (customer_id) REFERENCES customers(id))""")
    c.execute("CREATE INDEX idx_sales_date ON sales(date)")
    c.execute("CREATE INDEX idx_sales_region ON sales(region)")
    c.execute("CREATE INDEX idx_orders_date ON orders(order_date)")

    # 产品
    c.executemany("INSERT INTO products (name, category, price, cost) VALUES (?, ?, ?, ?)", PRODUCTS)

    # 客户
    base_date = datetime.now() - timedelta(days=365)
    customers = []
    for i in range(100):
        name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES)
        registered_at = base_date + timedelta(days=random.randint(0, 365))
        customers.append((name, random.choice(REGIONS), f"user{i+1}@example.com", registered_at.strftime("%Y-%m-%d")))
    c.executemany("INSERT INTO customers (name, region, email, registered_at) VALUES (?, ?, ?, ?)", customers)

    # 销售
    today = datetime.now()
    sales = []
    for month_offset in range(12, 0, -1):
        month_date = today - timedelta(days=month_offset * 30)
        month = month_date.month
        seasonal = 1.5 if month in [11, 12, 1] else (0.8 if month in [6, 7, 8] else 1.0)
        growth = 1 + (12 - month_offset) * 0.03
        for _ in range(int(random.randint(40, 80) * seasonal * growth)):
            day = random.randint(1, 28)
            sale_date = month_date.replace(day=min(day, 28))
            pid = random.randint(1, len(PRODUCTS))
            qty = random.randint(1, 5)
            price = PRODUCTS[pid - 1][2]
            sales.append((sale_date.strftime("%Y-%m-%d"), pid, random.randint(1, 100), qty, price, price * qty, random.choice(REGIONS)))
    c.executemany("INSERT INTO sales (date, product_id, customer_id, quantity, unit_price, amount, region) VALUES (?, ?, ?, ?, ?, ?, ?)", sales)

    # 订单
    orders = []
    for i in range(200):
        order_date = today - timedelta(days=random.randint(0, 180))
        r = random.random()
        status = "已完成" if r < 0.70 else ("已发货" if r < 0.85 else ("处理中" if r < 0.95 else "已取消"))
        orders.append((f"ORD{order_date.strftime('%Y%m%d')}{i+1:04d}", order_date.strftime("%Y-%m-%d"), random.randint(1, 100), round(random.uniform(1000, 50000), 2), status))
    c.executemany("INSERT INTO orders (order_no, order_date, customer_id, total_amount, status) VALUES (?, ?, ?, ?, ?)", orders)

    conn.commit()
    conn.close()
    print(f"  demo.db created: {demo_path}")
    return demo_path


def build_querygpt_db(demo_db_path: str):
    """生成预填充的 querygpt.db（连接 + 术语 + AppSettings）"""
    db_path = os.path.join(DATA_DIR, "querygpt.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # 建表（与 SQLAlchemy 模型对应）
    c.execute("""CREATE TABLE connections (
        id CHAR(32) PRIMARY KEY, name VARCHAR(100) NOT NULL, driver VARCHAR(20) NOT NULL,
        host VARCHAR(255), port INTEGER, username VARCHAR(100), password_encrypted TEXT,
        database_name VARCHAR(100), extra_options JSON DEFAULT '{}', is_default BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE models (
        id CHAR(32) PRIMARY KEY, name VARCHAR(100) NOT NULL, provider VARCHAR(50) NOT NULL,
        model_id VARCHAR(100) NOT NULL, base_url VARCHAR(500), api_key_encrypted TEXT,
        extra_options JSON DEFAULT '{}', is_default BOOLEAN DEFAULT 0, is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE conversations (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) REFERENCES connections(id) ON DELETE SET NULL,
        model_id CHAR(32) REFERENCES models(id) ON DELETE SET NULL,
        title VARCHAR(200), status VARCHAR(20) DEFAULT 'active', is_favorite BOOLEAN DEFAULT 0,
        extra_data JSON DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX idx_conversations_status ON conversations(status)")

    c.execute("""CREATE TABLE messages (
        id CHAR(32) PRIMARY KEY,
        conversation_id CHAR(32) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL, content TEXT NOT NULL, extra_data JSON DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX idx_messages_conversation ON messages(conversation_id)")

    c.execute("""CREATE TABLE app_settings (
        id INTEGER PRIMARY KEY,
        default_model_id CHAR(32) REFERENCES models(id) ON DELETE SET NULL,
        default_connection_id CHAR(32) REFERENCES connections(id) ON DELETE SET NULL,
        context_rounds INTEGER DEFAULT 5, python_enabled BOOLEAN DEFAULT 1,
        diagnostics_enabled BOOLEAN DEFAULT 1, auto_repair_enabled BOOLEAN DEFAULT 1,
        demo_initialized BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE semantic_terms (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) REFERENCES connections(id) ON DELETE CASCADE,
        term VARCHAR(100) NOT NULL, expression TEXT NOT NULL, term_type VARCHAR(20) DEFAULT 'metric',
        description TEXT, examples JSON DEFAULT '[]', is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX idx_semantic_terms_term ON semantic_terms(term)")

    c.execute("""CREATE TABLE table_relationships (
        id CHAR(32) PRIMARY KEY,
        connection_id CHAR(32) NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
        source_table VARCHAR(100) NOT NULL, source_column VARCHAR(100) NOT NULL,
        target_table VARCHAR(100) NOT NULL, target_column VARCHAR(100) NOT NULL,
        relationship_type VARCHAR(10) DEFAULT '1:N', join_type VARCHAR(20) DEFAULT 'LEFT',
        description TEXT, is_active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE prompts (
        id CHAR(32) PRIMARY KEY, name VARCHAR(100) NOT NULL, content TEXT NOT NULL,
        description TEXT, version INTEGER DEFAULT 1, is_active BOOLEAN DEFAULT 1,
        is_default BOOLEAN DEFAULT 0,
        parent_id CHAR(32) REFERENCES prompts(id) ON DELETE SET NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    # 插入 demo connection（database_name 用占位符，运行时替换）
    conn_id = uuid4().hex
    c.execute(
        "INSERT INTO connections (id, name, driver, database_name, extra_options, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (conn_id, "Sample Database", "sqlite", "__DEMO_DB_PATH__", "{}", 1, now, now),
    )

    # 插入 demo semantic terms
    for t in DEMO_SEMANTIC_TERMS:
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


if __name__ == "__main__":
    print("=== Seeding databases for desktop build ===")
    build_demo_db()
    build_querygpt_db(os.path.join(DATA_DIR, "demo.db"))
    print("Done.")
