"""
Analyst: Pulls top-scored items from the database, sends to Claude API
with the editorial system prompt, generates a draft briefing.
"""

import sqlite3
import yaml
import os
import json
import logging
from datetime import datetime, timedelta
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'data', 'analyst.log')),
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


def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'briefing_prompt.md')
    with open(prompt_path, 'r') as f:
        return f.read()


def get_items_for_briefing(db, config, days=7):
    """Get the highest-relevance items from the past week."""
    min_score = config['scoring']['min_score_for_briefing']
    max_items = config['briefing']['max_items']
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    cursor = db.execute('''
        SELECT id, source_name, category, state, title, url, 
               summary, published_date, relevance_score,
               tier1_hits, tier2_hits, tier3_hits
        FROM items
        WHERE relevance_score >= ?
          AND collected_date > ?
          AND included_in_briefing = 0
        ORDER BY relevance_score DESC
        LIMIT ?
    ''', (min_score, cutoff, max_items))
    
    return cursor.fetchall()


def format_items_for_prompt(items):
    """Format collected items into a structured input for Claude."""
    formatted = []
    for item in items:
        t1 = json.loads(item['tier1_hits']) if item['tier1_hits'] else []
        t2 = json.loads(item['tier2_hits']) if item['tier2_hits'] else []
        
        formatted.append(f"""---
**{item['title']}**
Source: {item['source_name']} | Category: {item['category']} | Score: {item['relevance_score']}
URL: {item['url']}
Published: {item['published_date'] or 'Unknown'}
Key topics: {', '.join(t1 + t2)}
Summary: {item['summary'][:500] if item['summary'] else 'No summary available'}
""")
    
    return '\n'.join(formatted)


def generate_briefing(items, config, db):
    """Send items to Claude API and generate a briefing draft."""
    system_prompt = load_system_prompt()
    items_text = format_items_for_prompt(items)
    
    # Check for state bill data
    bills_text = ""
    try:
        cursor = db.execute('''
            SELECT bill_number, title, state, status, description, 
                   sponsors, last_action, last_action_date, url, relevance_score
            FROM state_bills
            WHERE relevance_score >= 10
            ORDER BY relevance_score DESC
            LIMIT 15
        ''')
        bills = cursor.fetchall()
        if bills:
            bills_text = "\n\n**Active State Legislation (from LegiScan):**\n"
            for b in bills:
                sponsors = json.loads(b['sponsors']) if b['sponsors'] else []
                sponsor_str = ", ".join(sponsors[:3]) if sponsors else "Unknown"
                bills_text += f"""---
**{b['state']} {b['bill_number']}: {b['title']}**
Status: {b['status']} | Score: {b['relevance_score']}
Sponsors: {sponsor_str}
Last Action: {b['last_action']} ({b['last_action_date']})
URL: {b['url']}
Description: {b['description'][:300] if b['description'] else 'No description'}
"""
            log.info(f"Including {len(bills)} state bills in briefing")
    except Exception as e:
        log.info(f"No state bill data available: {e}")
    
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    
    user_prompt = f"""Generate this week's LegislAItive Report briefing.

**Period:** {week_ago.strftime('%B %d')} – {today.strftime('%B %d, %Y')}

**Collected Intelligence ({len(items)} items):**

{items_text}
{bills_text}

Generate the full briefing now. Remember: write for busy legislators and policy staff 
who need to know what happened, why it matters, and what's coming next.
If state bill data is included above, use it in the Model Legislation Watch section."""

    log.info(f"Sending {len(items)} items to Claude API for analysis...")
    
    # Use requests directly (anaconda httpx has SSL issues)
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": config['anthropic']['api_key'],
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        },
        json={
            "model": config['anthropic']['model'],
            "max_tokens": 4000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        },
        timeout=120
    )
    response.raise_for_status()
    data = response.json()
    
    briefing_text = data['content'][0]['text']
    
    input_tokens = data['usage']['input_tokens']
    output_tokens = data['usage']['output_tokens']
    cost_estimate = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)
    
    log.info(f"Briefing generated: {output_tokens} tokens, ~${cost_estimate:.4f}")
    
    return briefing_text, cost_estimate, input_tokens, output_tokens


def save_briefing(db, briefing_text, items, cost_estimate):
    """Save the generated briefing and mark items as included."""
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    
    cursor = db.execute('''
        INSERT INTO briefings 
        (created_date, period_start, period_end, status, content_markdown, 
         items_count, api_cost_estimate)
        VALUES (?, ?, ?, 'draft', ?, ?, ?)
    ''', (
        today.isoformat(),
        week_ago.isoformat(),
        today.isoformat(),
        briefing_text,
        len(items),
        cost_estimate
    ))
    
    briefing_id = cursor.lastrowid
    
    item_ids = [item['id'] for item in items]
    for item_id in item_ids:
        db.execute('''
            UPDATE items SET included_in_briefing = 1, briefing_id = ?
            WHERE id = ?
        ''', (briefing_id, item_id))
    
    db.commit()
    return briefing_id


def write_draft_file(briefing_text, briefing_id):
    """Write the briefing to a markdown file for editorial review."""
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output', 'drafts')
    os.makedirs(output_dir, exist_ok=True)
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"briefing-{date_str}-{briefing_id:04d}.md"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write(briefing_text)
    
    log.info(f"Draft written to: {filepath}")
    return filepath


def run_analysis():
    """Main analysis pipeline."""
    config = load_config()
    db = get_db(config)
    
    log.info("=" * 60)
    log.info("LegislAItive Report — Briefing Generation")
    log.info("=" * 60)
    
    items = get_items_for_briefing(db, config)
    
    if not items:
        log.warning("No items meet the relevance threshold. Skipping briefing generation.")
        log.info("Consider lowering min_score_for_briefing or adding more feeds.")
        db.close()
        return
    
    log.info(f"Found {len(items)} items for this briefing")
    
    briefing_text, cost_estimate, in_tok, out_tok = generate_briefing(items, config, db)
    briefing_id = save_briefing(db, briefing_text, items, cost_estimate)
    filepath = write_draft_file(briefing_text, briefing_id)
    
    log.info(f"\n✅ Briefing #{briefing_id} generated")
    log.info(f"   Items analyzed: {len(items)}")
    log.info(f"   API cost: ~${cost_estimate:.4f}")
    log.info(f"   Draft: {filepath}")
    log.info(f"\n   → Review the draft, edit as needed, then run publisher.py")
    
    db.close()


if __name__ == '__main__':
    run_analysis()
