# LegislAItive Report

AI-powered policy intelligence briefings for state and local government leaders.

## Architecture

```
[RSS Feeds / News APIs] → collector.py → SQLite DB
                                              ↓
                                        analyst.py (Claude API) → Draft Briefing
                                              ↓
                                        output/drafts/ → Editorial Review
                                              ↓
                                        publisher.py → Email Platform + Archive
```

## Setup

1. Clone to your machine
2. `pip install -r requirements.txt`
3. Copy `config/config.example.yaml` to `config/config.yaml` and add your API keys
4. Initialize the database: `python src/init_db.py`
5. Run the collector: `python src/collector.py`
6. Generate a briefing: `python src/analyst.py`

## Cron Schedule (suggested)

```cron
# Collect intelligence twice daily
0 7,19 * * * cd /path/to/legislaitive-report && python src/collector.py

# Generate weekly briefing draft every Sunday at 8am
0 8 * * 0 cd /path/to/legislaitive-report && python src/analyst.py
```

## Project Structure

```
config/          - Configuration and API keys
data/            - SQLite database
output/drafts/   - Generated briefings awaiting review
output/published/- Approved briefings
src/             - Source code
templates/       - Briefing templates and system prompts
```
---

<p align="center"><em>Æ</em></p>
