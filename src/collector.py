"""
Collector: Ingests RSS feeds, scores relevance, stores in SQLite.
Run via cron twice daily.
"""

import feedparser
import requests
import sqlite3
import yaml
import os
import re
import json
import logging
from datetime import datetime, timedelta
from dateutil import parser as dateparser

FEED_TIMEOUT = 15  # seconds

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'data', 'collector.log')),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_db(config):
    db_path = os.path.join(os.path.dirname(__file__), '..', config['database']['path'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def keyword_match(kw_lower, text):
    """Match keyword with word boundaries to avoid substring false positives.
    E.g. 'OMES' should not match 'homes', 'Stitt' should not match 'stitching'."""
    # Use word boundary regex for short keywords (<=8 chars) to prevent
    # false positives from substring matches
    if len(kw_lower) <= 8:
        pattern = r'\b' + re.escape(kw_lower) + r'\b'
        return bool(re.search(pattern, text))
    # For longer phrases, simple substring is fine
    return kw_lower in text


def score_item(title, summary, content, config):
    """Score an item's relevance based on keyword tiers."""
    keywords = config['keywords']
    scoring = config['scoring']
    
    title_text = (title or '').lower()
    body_text = f"{(summary or '')} {(content or '')}".lower()
    
    score = 0
    tier1_hits = []
    tier2_hits = []
    tier3_hits = []
    
    for kw in keywords.get('tier1', []):
        kw_lower = kw.lower()
        if keyword_match(kw_lower, title_text):
            score += scoring['tier1_weight'] * scoring['title_multiplier']
            tier1_hits.append(kw)
        elif keyword_match(kw_lower, body_text):
            score += scoring['tier1_weight']
            tier1_hits.append(kw)
    
    for kw in keywords.get('tier2', []):
        kw_lower = kw.lower()
        if keyword_match(kw_lower, title_text):
            score += scoring['tier2_weight'] * scoring['title_multiplier']
            tier2_hits.append(kw)
        elif keyword_match(kw_lower, body_text):
            score += scoring['tier2_weight']
            tier2_hits.append(kw)
    
    for kw in keywords.get('tier3', []):
        kw_lower = kw.lower()
        if keyword_match(kw_lower, title_text):
            score += scoring['tier3_weight'] * scoring['title_multiplier']
            tier3_hits.append(kw)
        elif keyword_match(kw_lower, body_text):
            score += scoring['tier3_weight']
            tier3_hits.append(kw)
    
    return score, tier1_hits, tier2_hits, tier3_hits


def parse_date(date_str):
    """Safely parse various date formats from RSS feeds."""
    if not date_str:
        return None
    try:
        return dateparser.parse(date_str).isoformat()
    except (ValueError, TypeError):
        return None


def collect_feed(feed_config, config, db):
    """Collect items from a single RSS feed."""
    feed_name = feed_config['name']
    feed_url = feed_config['url']
    category = feed_config.get('category', 'general')
    state = feed_config.get('state', None)
    
    log.info(f"Collecting: {feed_name}")
    
    try:
        # Fetch with timeout using requests, then parse
        resp = requests.get(feed_url, timeout=FEED_TIMEOUT, headers={
            'User-Agent': 'LegislAItive-Report/1.0 (Policy Intelligence Collector)'
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        
        if feed.bozo and not feed.entries:
            raise Exception(f"Feed parse error: {feed.bozo_exception}")
        
        new_items = 0
        for entry in feed.entries:
            url = entry.get('link', '')
            if not url:
                continue
            
            title = entry.get('title', 'Untitled')
            summary = entry.get('summary', '')
            content = ''
            if entry.get('content'):
                content = entry.content[0].get('value', '')
            
            clean_summary = re.sub(r'<[^>]+>', '', summary)
            clean_content = re.sub(r'<[^>]+>', '', content)
            
            published = parse_date(entry.get('published', entry.get('updated', '')))
            
            score, t1, t2, t3 = score_item(title, clean_summary, clean_content, config)
            
            if published:
                try:
                    pub_dt = dateparser.parse(published)
                    if pub_dt and (datetime.now(pub_dt.tzinfo) - pub_dt) < timedelta(hours=24):
                        score += config['scoring']['recency_bonus']
                except:
                    pass
            
            try:
                db.execute('''
                    INSERT OR IGNORE INTO items 
                    (source_name, source_url, category, state, title, url, 
                     summary, content, published_date, collected_date,
                     relevance_score, tier1_hits, tier2_hits, tier3_hits)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    feed_name, feed_url, category, state,
                    title, url, clean_summary[:1000], clean_content[:5000],
                    published, datetime.now().isoformat(),
                    score, json.dumps(t1), json.dumps(t2), json.dumps(t3)
                ))
                if db.total_changes:
                    new_items += 1
            except sqlite3.IntegrityError:
                pass
        
        db.commit()
        
        db.execute('''
            INSERT OR REPLACE INTO feed_status 
            (feed_name, last_checked, last_success, items_collected, consecutive_failures)
            VALUES (?, ?, ?, 
                    COALESCE((SELECT items_collected FROM feed_status WHERE feed_name = ?), 0) + ?,
                    0)
        ''', (feed_name, datetime.now().isoformat(), datetime.now().isoformat(),
              feed_name, new_items))
        db.commit()
        
        log.info(f"  → {feed_name}: {new_items} new items ({len(feed.entries)} total in feed)")
        return new_items
        
    except Exception as e:
        log.error(f"  ✗ {feed_name}: {e}")
        db.execute('''
            INSERT OR REPLACE INTO feed_status 
            (feed_name, last_checked, last_error, consecutive_failures)
            VALUES (?, ?, ?,
                    COALESCE((SELECT consecutive_failures FROM feed_status WHERE feed_name = ?), 0) + 1)
        ''', (feed_name, datetime.now().isoformat(), str(e), feed_name))
        db.commit()
        return 0


def collect_all():
    """Run collection across all configured feeds."""
    config = load_config()
    db = get_db(config)
    
    log.info("=" * 60)
    log.info("LegislAItive Report — Collection Run")
    log.info("=" * 60)
    
    total_new = 0
    for feed_config in config['feeds']:
        total_new += collect_feed(feed_config, config, db)
    
    cursor = db.execute('''
        SELECT title, relevance_score, source_name 
        FROM items 
        WHERE collected_date > ? AND relevance_score >= ?
        ORDER BY relevance_score DESC
        LIMIT 10
    ''', (
        (datetime.now() - timedelta(hours=24)).isoformat(),
        config['scoring']['min_score_for_briefing']
    ))
    
    hot_items = cursor.fetchall()
    if hot_items:
        log.info(f"\n🔥 High-relevance items from this run:")
        for item in hot_items:
            log.info(f"  [{item['relevance_score']:.0f}] {item['title']} ({item['source_name']})")
    
    log.info(f"\nCollection complete: {total_new} new items")
    db.close()


if __name__ == '__main__':
    collect_all()
