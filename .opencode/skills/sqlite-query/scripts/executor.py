import sys
import sqlite3
import re


def strip_comments(sql):
    lines = sql.split('\n')
    result = []
    for line in lines:
        line = re.sub(r'--.*$', '', line)
        result.append(line)
    sql = '\n'.join(result)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql


def remove_quoted_strings(sql):
    sql = re.sub(r"'[^']*'", '', sql)
    sql = re.sub(r'"[^"]*"', '', sql)
    return sql


BLOCKED_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
    'REPLACE', 'VACUUM', 'TRUNCATE', 'ATTACH', 'DETACH',
]


def is_safe(sql):
    cleaned = remove_quoted_strings(sql)
    cleaned = strip_comments(cleaned)

    statements = cleaned.split(';')
    for stmt in statements:
        stmt = stmt.strip().upper()
        if not stmt:
            continue

        for kw in BLOCKED_KEYWORDS:
            if stmt.startswith(kw):
                return False, kw

        if not (stmt.startswith('SELECT') or stmt.startswith('WITH') or
                stmt.startswith('EXPLAIN') or stmt.startswith('PRAGMA')):
            return False, None

    return True, None


def format_markdown(rows, description):
    headers = [d[0] for d in description]
    lines = []
    lines.append('| ' + ' | '.join(headers) + ' |')
    lines.append('|' + ' --- |' * len(headers))
    for row in rows:
        cells = ['NULL' if cell is None else str(cell) for cell in row]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python executor.py <db_path> "<SQL>"')
        sys.exit(1)

    db_path = sys.argv[1]
    sql = sys.argv[2]

    safe, blocked_keyword = is_safe(sql)
    if not safe:
        if blocked_keyword:
            print(f'ERROR: Modifying queries ({blocked_keyword}) are blocked.')
        else:
            print('ERROR: Only SELECT, WITH, EXPLAIN, and PRAGMA queries are allowed.')
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if rows:
            print(format_markdown(rows, cur.description))
        else:
            print('(empty set)')
    except Exception as e:
        print(f'SQL Error: {e}')
        sys.exit(1)
    finally:
        if conn:
            conn.close()
