"""Açık şıklı sorunun doğru satırının ekran y'sini (fiziksel piksel) basar.

Şıklar her soruda karıştığı için kayıt betiği doğru şıkkı backend'in kaydettiği son sorudan
(settings.last_question_json → correctIndex) okur. Kullanım: python3 -I choice_y.py  (LEXIS_DB ortamdan)
"""
import json
import os
import sqlite3

ROW_Y0, ROW_STEP, ROW_H = 134, 44, 36  # ilk şık satırının üstü ve satır aralığı (1920x1080 @1.25)

con = sqlite3.connect(os.environ["LEXIS_DB"])
q = json.loads(con.execute("SELECT value FROM settings WHERE key = 'last_question_json'").fetchone()[0])
print(ROW_Y0 + int(q["correctIndex"]) * ROW_STEP + ROW_H // 2)
