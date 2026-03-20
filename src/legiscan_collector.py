"""
LegiScan Collector: Searches state legislatures for AI-related bills.
Uses free LegiScan API (30,000 queries/month).
Register for key at: https://legiscan.com/legiscan

This is the killer feature — tracking actual legislation,
not just news about legislation.
"""

import requests
import sqlite3
import yaml
import os
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'data', 'legiscan.log')),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

BASE_URL = "https://api.legiscan.com/"

# Bill status codes
BILL_STATUS = {
    1: "Introduced", 2: "Engrossed", 3: "Enrolled",
    4: "Passed", 5: "Vetoed", 6: "Failed/Dead"
}

# AI-related search queries for state legislatures
AI_SEARCH_QUERIES = [
    "artificial intelligence",
    "algorithmic",
    "automated decision",
    "facial recognition",
    "deepfake",
    "machine learning",
    "generative AI",
    "AI governance",
    "data privacy",
    "surveillance technology",
]

# States to track (start with Oklahoma, expand as needed)
DEFAULT_STATES = ["OK"]


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_db(config):
    db_path = os.path.join(os.path.dirname(__file__), '..', config['database']['path'])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_legiscan_table(db):
    """Create table for tracking state bills if it doesn't exist."""
    db.execute('''
        CREATE TABLE IF NOT EXISTS state_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            legiscan_bill_id INTEGER UNIQUE,
            state TEXT NOT NULL,
            bill_number TEXT NOT NULL,
            title TEXT,
            description TEXT,
            status TEXT,
            status_date TEXT,
            url TEXT,
            state_url TEXT,
            search_query TEXT,
            relevance_score REAL DEFAULT 0,
            sponsors TEXT,
            last_action TEXT,
            last_action_date TEXT,
            collected_date TEXT NOT NULL,
            included_in_briefing INTEGER DEFAULT 0,
            change_hash TEXT
        )
    ''')
    db.commit()


def legiscan_search(api_key, state, query, year=2):
    """Search LegiScan for bills matching a query in a given state.
    year: 1=all, 2=current(default), 3=recent, 4=prior
    """
    params = {
        "key": api_key,
        "op": "search",
        "state": state,
        "query": query,
        "year": year,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") == "OK":
            results = data.get("searchresult", {})
            summary = results.pop("summary", {})
            bills = [results[k] for k in results if k != "summary"]
            return summary, bills
        else:
            log.warning(f"LegiScan API error: {data}")
            return None, []
    except Exception as e:
        log.error(f"LegiScan request failed: {e}")
        return None, []


def legiscan_get_bill(api_key, bill_id):
    """Get detailed bill information."""
    params = {
        "key": api_key,
        "op": "getBill",
        "id": bill_id,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK":
            return data.get("bill", {})
        return None
    except Exception as e:
        log.error(f"LegiScan getBill failed: {e}")
        return None


def score_bill(bill_data, search_query):
    """Score a bill's relevance for the briefing."""
    score = 0
    title = (bill_data.get("title", "") or "").lower()
    desc = (bill_data.get("description", "") or "").lower()
    
    # Direct AI mentions in title are highest value
    ai_terms = ["artificial intelligence", "ai ", "algorithmic",
                 "machine learning", "facial recognition", "deepfake",
                 "automated decision", "generative ai"]
    
    for term in ai_terms:
        if term in title:
            score += 30  # Title match = very high
        elif term in desc:
            score += 15  # Description match = high
    
    # Active bills worth more than dead ones
    status = bill_data.get("status", 0)
    if status in [1, 2, 3]:  # Introduced, Engrossed, Enrolled
        score += 10
    elif status == 4:  # Passed
        score += 20
    
    # Recency of last action
    if bill_data.get("last_action_date"):
        score += 5
    
    return max(score, 5)  # Minimum score of 5 for any match


def collect_state_bills(states=None):
    """Search LegiScan for AI-related bills across target states."""
    config = load_config()
    
    legiscan_key = config.get("legiscan", {}).get("api_key")
    if not legiscan_key or legiscan_key == "your-legiscan-key-here":
        log.error("No LegiScan API key configured.")
        log.info("Register for free at: https://legiscan.com/legiscan")
        log.info("Then add to config.yaml under legiscan.api_key")
        return
    
    db = get_db(config)
    init_legiscan_table(db)
    
    if states is None:
        states = config.get("legiscan", {}).get("states", DEFAULT_STATES)
    
    log.info("=" * 60)
    log.info("LegislAItive Report — State Bill Collection (LegiScan)")
    log.info("=" * 60)
    
    total_new = 0
    total_queries = 0
    
    for state in states:
        log.info(f"\n📜 Searching {state} legislature...")
        
        for query in AI_SEARCH_QUERIES:
            summary, bills = legiscan_search(legiscan_key, state, query)
            total_queries += 1
            
            if not bills:
                continue
            
            count = summary.get("count", 0) if summary else 0
            log.info(f"  '{query}': {count} results")
            
            for bill in bills:
                bill_id = bill.get("bill_id")
                if not bill_id:
                    continue
                
                # Check if we already have this bill
                existing = db.execute(
                    "SELECT id, change_hash FROM state_bills WHERE legiscan_bill_id = ?",
                    (bill_id,)
                ).fetchone()
                
                change_hash = bill.get("change_hash", "")
                
                if existing and existing["change_hash"] == change_hash:
                    continue  # No changes since last check
                
                # Get full bill details (costs 1 query)
                detail = legiscan_get_bill(legiscan_key, bill_id)
                total_queries += 1
                
                if not detail:
                    continue
                
                score = score_bill(detail, query)
                sponsors = json.dumps([
                    s.get("name", "") for s in detail.get("sponsors", [])
                ])
                
                history = detail.get("history", [])
                last_action = history[-1].get("action", "") if history else ""
                last_action_date = history[-1].get("date", "") if history else ""
                
                try:
                    db.execute('''
                        INSERT OR REPLACE INTO state_bills
                        (legiscan_bill_id, state, bill_number, title, description,
                         status, status_date, url, state_url, search_query,
                         relevance_score, sponsors, last_action, last_action_date,
                         collected_date, change_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        bill_id,
                        detail.get("state", state),
                        detail.get("bill_number", ""),
                        detail.get("title", ""),
                        detail.get("description", ""),
                        BILL_STATUS.get(detail.get("status", 0), "Unknown"),
                        detail.get("status_date", ""),
                        detail.get("url", ""),
                        detail.get("state_link", ""),
                        query,
                        score,
                        sponsors,
                        last_action,
                        last_action_date,
                        datetime.now().isoformat(),
                        change_hash
                    ))
                    total_new += 1
                except Exception as e:
                    log.error(f"  DB error for {bill_id}: {e}")
                
                db.commit()
    
    # Report findings
    cursor = db.execute('''
        SELECT bill_number, title, state, status, relevance_score
        FROM state_bills
        ORDER BY relevance_score DESC
        LIMIT 15
    ''')
    
    top_bills = cursor.fetchall()
    if top_bills:
        log.info(f"\n🏛️  Top AI-related bills tracked:")
        for b in top_bills:
            log.info(f"  [{b['relevance_score']:.0f}] {b['state']} {b['bill_number']}: "
                     f"{b['title'][:80]} ({b['status']})")
    
    log.info(f"\nLegiScan collection complete: {total_new} new/updated bills, "
             f"{total_queries} API queries used")
    db.close()


if __name__ == '__main__':
    import sys
    states = sys.argv[1:] if len(sys.argv) > 1 else None
    collect_state_bills(states)
