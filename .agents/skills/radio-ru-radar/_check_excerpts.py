import sqlite3
db = sqlite3.connect('data/radio.db')
cur = db.execute('SELECT COUNT(*) FROM articles WHERE excerpt IS NULL OR excerpt = ""')
print(f'Bez excerpt: {cur.fetchone()[0]}')
cur = db.execute('SELECT COUNT(*) FROM articles')
print(f'Vsego: {cur.fetchone()[0]}')
cur = db.execute('SELECT year, month, COUNT(*) FROM articles WHERE excerpt IS NULL OR excerpt = "" GROUP BY year, month ORDER BY year DESC, month DESC')
for row in cur.fetchall():
    print(f'  {row[0]}-{row[1]:02d}: {row[2]} statey bez excerpt')
db.close()