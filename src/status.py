"""Quick status check on the intelligence database."""

import sqlite3
import yaml
import os
from datetime import datetime, timedelta

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def status():
    config = load_config()
    db_path = os.path.join(os.path.dirname(__file__), '..', config['database']['path'])
    
    if not os.path.exists(db_path):
        print("Database not initialized. Run: python src/init_db.py")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    total = conn.execute('SELECT COUNT(*) as c FROM items').fetchone()['c']
    
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    this_week = conn.execute(
        'SELECT COUNT(*) as c FROM items WHERE collected_date > ?', (week_ago,)
    ).fetchone()['c']
    
    min_score = config['scoring']['min_score_for_briefing']
    high_rel = conn.execute(
        'SELECT COUNT(*) as c FROM items WHERE relevance_score >= ? AND collected_date > ?',
        (min_score, week_ago)
    ).fetchone()['c']
    
    briefings = conn.execute('SELECT COUNT(*) as c FROM briefings').fetchone()['c']
    feeds = conn.execute('SELECT * FROM feed_status ORDER BY last_checked DESC').fetchall()
    
    print("=" * 60)
    print("LegislAItive Report — System Status")
    print("=" * 60)
    print(f"\n📊 Database: {total} total items")
    print(f"   This week: {this_week} items collected")
    print(f"   Briefing-ready (score ≥ {min_score}): {high_rel} items")
    print(f"   Briefings generated: {briefings}")
    
    print(f"\n📡 Feed Status:")
    for feed in feeds:
        status_icon = "✅" if feed['consecutive_failures'] == 0 else f"⚠️ ({feed['consecutive_failures']} failures)"
        print(f"   {status_icon} {feed['feed_name']}: {feed['items_collected']} items total")
    
    top_items = conn.execute('''
        SELECT title, relevance_score, source_name, url
        FROM items 
        WHERE collected_date > ?
        ORDER BY relevance_score DESC
        LIMIT 10
    ''', (week_ago,)).fetchall()
    
    if top_items:
        print(f"\n🔥 Top items this week:")
        for item in top_items:
            print(f"   [{item['relevance_score']:.0f}] {item['title'][:70]}")
            print(f"        {item['source_name']} — {item['url'][:60]}")
    
    conn.close()

if __name__ == '__main__':
    status()
