SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scrape_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT DEFAULT 'running',
    total_pages     INTEGER,
    total_found     INTEGER,
    full_text_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    page_number     INTEGER NOT NULL,
    session_id      INTEGER REFERENCES scrape_sessions(id),
    scraped_at      TEXT NOT NULL,
    status          TEXT DEFAULT 'done',
    article_count   INTEGER,
    retry_count     INTEGER DEFAULT 0,
    error_message   TEXT,
    UNIQUE(category, page_number)
);

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    author          TEXT,
    date            TEXT,
    excerpt         TEXT,
    content_raw     TEXT,
    content_md      TEXT,
    tags            TEXT,
    content_hash    TEXT,
    session_id      INTEGER REFERENCES scrape_sessions(id),
    loaded_at       TEXT NOT NULL,
    article_scraped_at TEXT,
    status          TEXT DEFAULT 'metadata',
    UNIQUE(category, url)
);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    article_url     TEXT NOT NULL,
    author          TEXT,
    date            TEXT,
    content_md      TEXT
);

CREATE TABLE IF NOT EXISTS analysis_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    query_hash      TEXT NOT NULL,
    query_name      TEXT,
    query_text      TEXT,
    rubric_hash     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    passed_filter   INTEGER,
    filter_reason   TEXT,
    scores_json     TEXT,
    total           INTEGER,
    comment         TEXT,
    attempts        INTEGER DEFAULT 0,
    last_error      TEXT,
    filtered_at     TEXT,
    scored_at       TEXT,
    UNIQUE(article_id, query_hash, rubric_hash, content_hash)
);
"""

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)",
    "CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date)",
    "CREATE INDEX IF NOT EXISTS idx_articles_loaded ON articles(loaded_at)",
    "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)",
    "CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)",
    "CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_category ON scrape_sessions(category)",
    "CREATE INDEX IF NOT EXISTS idx_comments_article ON comments(article_id)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_query_rubric_total ON analysis_scores(query_hash, rubric_hash, total)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_query_rubric_status ON analysis_scores(query_hash, rubric_hash, status)",
    "CREATE INDEX IF NOT EXISTS idx_analysis_article ON analysis_scores(article_id)",
]