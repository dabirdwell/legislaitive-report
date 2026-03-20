"""Initialize the SQLite database for intelligence storage."""

import sqlite3
import os
import yaml

def get_db_path():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    db_path = os.path.join(os.path.dirname(__file__), '..', config['database']['path'])
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Raw collected items from RSS/news sources
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_url TEXT,
            category TEXT,
            state TEXT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            summary TEXT,
            content TEXT,
            published_date TEXT,
            collected_date TEXT NOT NULL,
            relevance_score REAL DEFAULT 0,
            tier1_hits TEXT,
            tier2_hits TEXT,
            tier3_hits TEXT,
            included_in_briefing INTEGER DEFAULT 0,
            briefing_id INTEGER,
            FOREIGN KEY (briefing_id) REFERENCES briefings(id)
        )
    ''')

    # Generated briefings
    c.execute('''
        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_date TEXT NOT NULL,
            period_start TEXT,
            period_end TEXT,
            status TEXT DEFAULT 'draft',
            title TEXT,
            content_markdown TEXT,
            content_html TEXT,
            editorial_notes TEXT,
            items_count INTEGER,
            api_cost_estimate REAL,
            published_date TEXT
        )
    ''')

    # Track feed health
    c.execute('''
        CREATE TABLE IF NOT EXISTS feed_status (
            feed_name TEXT PRIMARY KEY,
            last_checked TEXT,
            last_success TEXT,
            last_error TEXT,
            items_collected INTEGER DEFAULT 0,
            consecutive_failures INTEGER DEFAULT 0
        )
    ''')

    # Keyword tracking for trend analysis
    c.execute('''
        CREATE TABLE IF NOT EXISTS keyword_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            week_start TEXT NOT NULL,
            occurrence_count INTEGER DEFAULT 0,
            avg_relevance REAL DEFAULT 0,
            UNIQUE(keyword, week_start)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized at {db_path}")

if __name__ == '__main__':
    init_db()
