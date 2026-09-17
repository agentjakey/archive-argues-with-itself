import sqlite3
p = r"data\exploration\microlog\index\vectors_microlog.db"
c = sqlite3.connect(p)
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for t in tables:
    try:
        print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
    except Exception as e:
        print(t, "count failed:", e)
