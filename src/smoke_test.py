"""
Smoke test: Run the collector on a single feed to verify the pipeline works.
Does NOT require an Anthropic API key — just tests collection and scoring.
"""

import os
import sys
import yaml
import shutil
import tempfile

TEST_CONFIG = {
    'feeds': [
        {
            'name': 'Government Technology',
            'url': 'https://www.govtech.com/rss',
            'category': 'govtech'
        },
        {
            'name': 'StateScoop',
            'url': 'https://statescoop.com/feed/',
            'category': 'govtech'
        }
    ],
    'keywords': {
        'tier1': ['artificial intelligence', 'AI regulation', 'AI policy', 
                  'algorithmic', 'automated decision', 'generative AI'],
        'tier2': ['data privacy', 'cybersecurity', 'government technology',
                  'digital government'],
        'tier3': ['technology procurement', 'IT modernization']
    },
    'scoring': {
        'tier1_weight': 10,
        'tier2_weight': 5,
        'tier3_weight': 2,
        'title_multiplier': 3,
        'recency_bonus': 5,
        'min_score_for_briefing': 8
    },
    'briefing': {
        'max_items': 20
    },
    'database': {
        'path': 'data/intelligence.db'
    }
}

def run_test():
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    config_path = os.path.join(config_dir, 'config.yaml')
    
    backup_path = None
    if os.path.exists(config_path):
        backup_path = config_path + '.bak'
        shutil.copy2(config_path, backup_path)
    
    try:
        with open(config_path, 'w') as f:
            yaml.dump(TEST_CONFIG, f)
        
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        print("1️⃣  Initializing database...")
        from init_db import init_db
        init_db()
        
        print("\n2️⃣  Running collector on test feeds...")
        from collector import collect_all
        collect_all()
        
        print("\n3️⃣  Checking status...")
        from status import status
        status()
        
        print("\n✅ Smoke test complete!")
        print("   If you see items above, the pipeline is working.")
        print("   Next: add your Anthropic API key to config/config.yaml")
        print("   Then: python src/analyst.py to generate your first briefing")
        
    finally:
        if backup_path and os.path.exists(backup_path):
            shutil.move(backup_path, config_path)

if __name__ == '__main__':
    run_test()
