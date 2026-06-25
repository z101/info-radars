# Info Radar

Scrapes and analyzes articles from multiple blog/feed websites for topic relevance.

Each site has its own **self-contained radar skill** under `.agents/skills/<site>-radar/` with its own `SKILL.md`, scraper, tests, and runtime data.

## Included Radars

| Site | Skill | Status |
|------|-------|--------|
| [Hackaday LED Hacks](https://hackaday.com/category/led-hacks/) | `.agents/skills/hackaday-blog-radar/` | Active |

## Quick Start

```bash
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Navigate to the skill directory
cd .agents\skills\hackaday-blog-radar

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify with dry run
python hackaday_blog_radar.py --category led-hacks --dry-run

# 5. Full scrape
python hackaday_blog_radar.py --category led-hacks
```

## Project Structure

```
info-radar/
├── .venv/                         # shared virtual environment
├── .agents/
│   ├── skills/
│   │   ├── hackaday-blog-radar/    # self-contained radar skill
│   │   │   ├── SKILL.md           # AI instructions
│   │   │   ├── hackaday_blog_radar.py  # entry point
│   │   │   ├── scraper/           # scraping engine
│   │   │   ├── tests/             # pytest suite
│   │   │   ├── data/              # SQLite database
│   │   └── info-radar-generator/  # meta-skill for scaffolding new radars
│   └── node_modules/
├── .gitignore
├── AGENTS.md
└── README.md
```