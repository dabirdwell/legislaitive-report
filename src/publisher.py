"""
Publisher: Takes an approved briefing and delivers it.
Phase 1: Just copies to published/ folder
Phase 2: Sends via email platform API (Buttondown/Beehiiv)
Phase 3: Also posts highlights to social media
"""

import sqlite3
import yaml
import os
import shutil
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
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


def publish(draft_path):
    """Move a reviewed draft to published and update the database."""
    config = load_config()
    db = get_db(config)
    
    if not os.path.exists(draft_path):
        log.error(f"Draft not found: {draft_path}")
        return
    
    published_dir = os.path.join(os.path.dirname(__file__), '..', 'output', 'published')
    os.makedirs(published_dir, exist_ok=True)
    
    filename = os.path.basename(draft_path)
    published_path = os.path.join(published_dir, filename)
    shutil.move(draft_path, published_path)
    
    log.info(f"✅ Published: {published_path}")
    
    try:
        briefing_id = int(filename.split('-')[-1].replace('.md', ''))
        db.execute('''
            UPDATE briefings SET status = 'published', published_date = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), briefing_id))
        db.commit()
        log.info(f"   Database updated for briefing #{briefing_id}")
    except (ValueError, IndexError):
        log.warning("   Could not extract briefing ID from filename — database not updated")
    
    db.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python publisher.py <path-to-draft.md>")
        print("       Moves a reviewed draft to published status.")
        sys.exit(1)
    
    publish(sys.argv[1])


def get_db(config):
    db_path = os.path.join(os.path.dirname(__file__), '..', config['database']['path'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def publish(draft_path):
    """Move a reviewed draft to published and update the database."""
    config = load_config()
    db = get_db(config)
    
    if not os.path.exists(draft_path):
        log.error(f"Draft not found: {draft_path}")
        return
    
    published_dir = os.path.join(os.path.dirname(__file__), '..', 'output', 'published')
    os.makedirs(published_dir, exist_ok=True)
    
    filename = os.path.basename(draft_path)
    published_path = os.path.join(published_dir, filename)
    shutil.move(draft_path, published_path)
    
    log.info(f"✅ Published: {published_path}")
    
    try:
        briefing_id = int(filename.split('-')[-1].replace('.md', ''))
        db.execute('''
            UPDATE briefings SET status = 'published', published_date = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), briefing_id))
        db.commit()
        log.info(f"   Database updated for briefing #{briefing_id}")
    except (ValueError, IndexError):
        log.warning("   Could not extract briefing ID from filename — database not updated")
    
    db.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python publisher.py <path-to-draft.md>")
        print("       Moves a reviewed draft to published status.")
        sys.exit(1)
    
    publish(sys.argv[1])
