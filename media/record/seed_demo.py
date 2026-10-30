"""README kaydı için demo veritabanı: başlangıç destesi + 30 günlük yapay cevap geçmişi.

LEXIS_DB / LEXIS_CONFIG / LEXIS_STATE_DIR ortamdan gelir; gerçek veriye dokunmaz.
Kullanım: python3 -I seed_demo.py <repo>
"""
import json
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

repo = Path(sys.argv[1])
cli = repo / "backend" / "lexis_cli.py"


def rpc(cmd: str, payload: dict) -> dict:
    out = subprocess.run(
        ["python3", "-I", str(cli), cmd, "-"],
        input=json.dumps(payload), capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


rpc("save-settings", {"language": "en", "intervalMin": 60, "dailyGoal": 50, "aiProvider": "off"})
assert rpc("load-starter", {})["added"] == 30

rnd = random.Random(7)
con = sqlite3.connect(rpc("snapshot", {})["dbPath"])
ids = [r[0] for r in con.execute("SELECT id FROM words ORDER BY id")]
qtypes = ("choice_word_meaning", "choice_meaning_word", "type_word_meaning", "type_context")
now = time.time()
day = 86400
# İlk 22 kelime farklı kutularda (öğrenilmekte/oturmuş); son 8'i hiç sorulmamış yeni kelime.
for i, wid in enumerate(ids[:22]):
    box = 0 if i < 6 else (2 if i < 14 else 4)
    con.execute("UPDATE words SET box = ?, due_at = ? WHERE id = ?", (box, now + rnd.randint(1, 5) * day, wid))
    con.execute(
        "INSERT INTO events(word_id, ts, qtype, result, answer) VALUES(?, ?, 'intro', 'intro', '')",
        (wid, now - rnd.randint(20, 29) * day),
    )
events = []
for d in range(29, -1, -1):
    for _ in range(0 if d % 7 == 5 else rnd.randint(6, 22) if d else 14):
        wid = rnd.choice(ids[:22])
        ok = rnd.random() < (0.62 if wid in ids[:6] else 0.88)
        ts = now - d * day - rnd.randint(0, 6 * 3600) if d else now - rnd.randint(60, 4 * 3600)
        events.append((wid, ts, rnd.choice(qtypes), "correct" if ok else "wrong", ""))
con.executemany("INSERT INTO events(word_id, ts, qtype, result, answer) VALUES(?, ?, ?, ?, ?)", events)
con.commit()
print(f"demo: {len(ids)} words, {len(events)} answers")
