import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "backend" / "lexis_cli.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class LexisCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = os.environ.copy()
        self.env["LEXIS_DB"] = os.path.join(self.tmp.name, "lexis.sqlite")
        self.env["LEXIS_CONFIG"] = os.path.join(self.tmp.name, "settings.json")
        self.env["LEXIS_STATE_DIR"] = os.path.join(self.tmp.name, "state")
        self.env["LEXIS_LEGACY_DB"] = os.path.join(self.tmp.name, "legacy_kelime.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def rpc(self, cmd: str, payload: dict | None = None, via_stdin: bool = True) -> dict:
        arg = "-" if via_stdin else json.dumps(payload or {}, ensure_ascii=False)
        proc = subprocess.run(
            ["python3", str(CLI), cmd, arg],
            env=self.env,
            input=(json.dumps(payload or {}, ensure_ascii=False) + "\n") if via_stdin else None,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(proc.stdout.strip())

    def test_srs_lifecycle_and_replace_question(self) -> None:
        snap = self.rpc("snapshot")
        self.assertTrue(snap["ok"])
        self.assertEqual(snap["settings"]["language"], "en")
        self.assertEqual(snap["settings"]["aiProvider"], "off")
        self.assertTrue(snap["settings"]["dictionaryEnabled"])
        self.assertEqual(snap["settings"]["intervalMin"], 5)
        self.assertEqual(snap["settings"]["dailyGoal"], 50)
        self.assertEqual(snap["settings"]["targetLang"], "English")
        self.assertEqual(snap["settings"]["meaningLang"], "Turkish")

        deck = [
            ("mitigate", "hafifletmek, azaltmak", "verb", "Soil cover helps mitigate erosion.", "Toprak örtüsü erozyonu hafifletmeye yardımcı olur."),
            ("scrutinize", "incelemek, irdelemek", "verb", "Auditors scrutinize every invoice.", "Denetçiler her faturayı inceler."),
            ("bolster", "güçlendirmek, desteklemek", "verb", "New evidence will bolster our claim.", "Yeni kanıt iddiamızı güçlendirecek."),
            ("curtail", "kısmak, sınırlandırmak", "verb", "The city voted to curtail noise.", "Şehir gürültüyü sınırlandırmaya oy verdi."),
            ("foster", "teşvik etmek, beslemek", "verb", "Open labs foster curiosity.", "Açık laboratuvarlar merakı besler."),
        ]
        ids = []
        for w, m, pos, ex, tr in deck:
            res = self.rpc(
                "add-word",
                {"word": w, "meaning": m, "pos": pos, "example": ex, "translation": tr, "listName": "Core"},
            )
            self.assertTrue(res["ok"])
            ids.append(res["wordId"])

        now = 1_700_000_000.0
        q1 = self.rpc("next-question", {"wordId": ids[0], "now": now})["question"]
        self.assertEqual(q1["qtype"], "intro")
        self.assertIn("mitigate", q1["title"])
        self.assertIn("<b>mitigate</b>", q1["bodyHtml"])
        self.assertIn("<i>", q1["bodyHtml"])

        # Replacing an unanswered intro card records it as intro (box -> 0) and draws next question
        q2 = self.rpc(
            "next-question",
            {"wordId": ids[1], "now": now + 300, "replaceQuestion": {"wordId": ids[0], "qtype": "intro"}},
        )["question"]
        self.assertEqual(q2["wordId"], ids[1])
        snap_after_replace = self.rpc("snapshot", {"selectedWordId": ids[0]})
        self.assertEqual(snap_after_replace["selectedWord"]["box"], 0)
        self.assertAlmostEqual(snap_after_replace["selectedWord"]["dueAt"], now + 300 + 600, places=1)

        # At box == 0, word[0] must emit a 4-choice question
        q_choice = self.rpc("next-question", {"wordId": ids[0], "now": now + 1000})["question"]
        self.assertIn(q_choice["qtype"], ("choice_word_meaning", "choice_meaning_word"))
        self.assertEqual(len(q_choice["choices"]), 4)

        # Replacing an unanswered quiz card logs 'skipped' without resetting box
        _ = self.rpc(
            "next-question",
            {"wordId": ids[1], "now": now + 1300, "replaceQuestion": {"wordId": ids[0], "qtype": q_choice["qtype"]}},
        )
        w0_hist = self.rpc("snapshot", {"selectedWordId": ids[0]})["selectedWord"]
        self.assertEqual(w0_hist["box"], 0)

        # Advance word[0] through boxes 0 -> 1 -> 2 -> 3 -> 4 -> 5 via correct answers
        expected_intervals = [1800, 7200, 86400, 3 * 86400, 7 * 86400]
        t_cur = now + 2000
        for expected_box, expected_delta in enumerate(expected_intervals, start=1):
            q_step = self.rpc("next-question", {"wordId": ids[0], "now": t_cur})["question"]
            if expected_box == 1:
                self.assertIn(q_step["qtype"], ("choice_word_meaning", "choice_meaning_word"))
            if q_step["qtype"].startswith("choice_"):
                g = self.rpc(
                    "grade-question",
                    {
                        "wordId": ids[0],
                        "qtype": q_step["qtype"],
                        "action": "choice",
                        "choiceIndex": q_step["correctIndex"],
                        "now": t_cur,
                    },
                )
            else:
                g = self.rpc(
                    "grade-question",
                    {
                        "wordId": ids[0],
                        "qtype": q_step["qtype"],
                        "action": "typed",
                        "typedText": "hafifletmek",
                        "now": t_cur,
                    },
                )
            self.assertEqual(g["result"], "correct")
            w0_state = self.rpc("snapshot", {"selectedWordId": ids[0]})["selectedWord"]
            self.assertEqual(w0_state["box"], expected_box)
            self.assertAlmostEqual(w0_state["dueAt"], t_cur + expected_delta, places=1)
            t_cur += expected_delta + 10

        # At box >= 4, questions are strictly typed
        for _ in range(5):
            q_settled = self.rpc("next-question", {"wordId": ids[0], "now": t_cur})["question"]
            self.assertIn(q_settled["qtype"], ("type_word_meaning", "type_context"))

        # Hiding removes from pool; unhiding restores
        self.rpc("grade-question", {"wordId": ids[0], "qtype": "type_word_meaning", "action": "hide", "now": t_cur})
        hidden_words = self.rpc("snapshot", {"listFilter": "__hidden__"})["words"]
        self.assertEqual([w["id"] for w in hidden_words], [ids[0]])
        self.rpc("set-hidden", {"wordId": ids[0], "hidden": False})
        self.assertEqual(self.rpc("snapshot", {"listFilter": "__hidden__"})["words"], [])

    def test_multilingual_answer_matching_and_short_word_guard(self) -> None:
        from backend.lexis_cli import match_answer

        self.assertTrue(match_answer("isik", "Işık, aydınlık"))
        self.assertTrue(match_answer("İSIK", "ışık"))
        self.assertTrue(match_answer("eclair", "éclair"))
        self.assertTrue(match_answer("grosse", "Größe"))
        self.assertFalse(match_answer("almak", "azalmak"))
        self.assertFalse(match_answer("far", "fair"))
        self.assertTrue(match_answer("hafifletmk", "hafifletmek"))
        self.assertTrue(match_answer("olusmak", "-den/-dan oluşmak"))
        self.assertFalse(match_answer("den", "-den/-dan oluşmak"))

        w_id = self.rpc(
            "add-word",
            {"word": "größe", "meaning": "boyut, büyüklük", "pos": "noun", "listName": "DE"},
        )["wordId"]
        self.rpc("grade-question", {"wordId": w_id, "qtype": "intro", "action": "intro", "now": 1000.0})

        # With aiProvider == 'off', a non-matching typed answer immediately records 'wrong'
        res_off = self.rpc(
            "grade-question",
            {"wordId": w_id, "qtype": "type_word_meaning", "action": "typed", "typedText": "alakasiz", "now": 2000.0},
        )
        self.assertEqual(res_off["status"], "recorded")
        self.assertEqual(res_off["result"], "wrong")

        # With aiProvider == 'custom' and baseUrl/model set, a non-matching typed answer requests async AI judge
        self.rpc(
            "save-settings",
            {"aiProvider": "custom", "customBaseUrl": "http://127.0.0.1:11434/v1", "customModel": "qwen2.5:3b"},
        )
        res_ai = self.rpc(
            "grade-question",
            {"wordId": w_id, "qtype": "type_word_meaning", "action": "typed", "typedText": "ebat", "now": 3000.0},
        )
        self.assertEqual(res_ai["status"], "needs_ai_judge")

    def test_distractor_overlap_and_small_deck_fallback(self) -> None:
        w1 = self.rpc("add-word", {"word": "accurate", "meaning": "doğru, kesin", "pos": "adjective"})["wordId"]
        w2 = self.rpc("add-word", {"word": "precise", "meaning": "kesin, tam", "pos": "adjective"})["wordId"]
        self.rpc("grade-question", {"wordId": w1, "qtype": "intro", "action": "intro", "now": 100.0})
        self.rpc("grade-question", {"wordId": w2, "qtype": "intro", "action": "intro", "now": 100.0})

        # Only 2 words exist -> even at box == 0, must fall back to typed instead of <4 choices
        q_small = self.rpc("next-question", {"wordId": w1, "now": 800.0})["question"]
        self.assertEqual(q_small["qtype"], "type_word_meaning")
        self.assertEqual(q_small["choices"], [])

        # Add 3 distinct non-overlapping words so 4-choice becomes possible, and verify 'precise' never appears as distractor for 'accurate'
        for w, m in [("swift", "hızlı"), ("fragile", "kırılgan"), ("opaque", "mat, saydam olmayan")]:
            wid = self.rpc("add-word", {"word": w, "meaning": m, "pos": "adjective"})["wordId"]
            self.rpc("grade-question", {"wordId": wid, "qtype": "intro", "action": "intro", "now": 100.0})

        for i in range(15):
            q = self.rpc("next-question", {"wordId": w1, "now": 900.0 + i})["question"]
            self.assertIn(q["qtype"], ("choice_word_meaning", "choice_meaning_word"))
            self.assertEqual(len(q["choices"]), 4)
            self.assertNotIn("precise", q["choices"])
            self.assertNotIn("kesin, tam", q["choices"])
            # 'kesin' alone isn't choice_label of precise ('kesin'), check 'kesin' not in choices!
            self.assertNotIn("kesin", q["choices"])

    def test_csv_sniffing_column_mapping_and_starter_deck(self) -> None:
        # 1. Semicolon CSV with header and custom column mapping [1, 0, 3, 2]
        csv_semi = Path(self.tmp.name) / "akademik.csv"
        csv_semi.write_text(
            "Anlam;Kelime;Çeviri;Örnek\n"
            "hafifletmek, azaltmak;mitigate;Toprak örtüsü erozyonu azaltır.;Soil cover helps mitigate erosion.\n"
            "incelemek;scrutinize;Denetçiler her satırı inceler.;Auditors scrutinize every line.\n",
            encoding="utf-8-sig",
        )
        prev = self.rpc("preview-import", {"path": str(csv_semi), "columns": [1, 0, 3, 2]})
        self.assertTrue(prev["ok"])
        self.assertEqual(prev["kind"], "csv")
        self.assertEqual(prev["total"], 2)
        self.assertEqual(prev["rows"][0]["word"], "mitigate")
        self.assertEqual(prev["rows"][0]["meaning"], "hafifletmek, azaltmak")
        self.assertEqual(prev["rows"][0]["example"], "Soil cover helps mitigate erosion.")

        imp = self.rpc("confirm-import", {"path": str(csv_semi), "listName": "Akademik", "columns": [1, 0, 3, 2]})
        self.assertEqual(imp["added"], 2)
        self.assertEqual(imp["skipped"], 0)

        # Duplicate import skips existing words
        imp_dup = self.rpc("confirm-import", {"path": str(csv_semi), "listName": "Akademik", "columns": [1, 0, 3, 2]})
        self.assertEqual(imp_dup["added"], 0)
        self.assertEqual(imp_dup["skipped"], 2)

        # 2. Headerless comma CSV where first row starts with literal English word 'word' (must NOT be dropped as header)
        csv_no_hdr = Path(self.tmp.name) / "plain.csv"
        csv_no_hdr.write_text("word,sözcük\nnovel,roman\n", encoding="utf-8")
        imp2 = self.rpc("confirm-import", {"path": str(csv_no_hdr)})
        self.assertEqual(imp2["added"], 2)

        # 3. Starter deck (30 words)
        starter = self.rpc("load-starter")
        self.assertTrue(starter["ok"])
        self.assertEqual(starter["total"], 30)
        self.assertGreaterEqual(starter["added"], 28)  # 'mitigate'/'scrutinize' may already exist

    def test_pdf_multiline_table_import_via_pdftotext(self) -> None:
        from backend.lexis_cli import parse_pdftotext_layout

        layout_text = (
            "                   YDS AKADEMİK FİİLLER LİSTESİ - 1\n"
            "Sıra  Fiil            Anlam                  Örnek Cümle                      Türkçe Çevirisi\n"
            "  1   mitigate        hafifletmek,           Soil conservation helps          Toprak koruma erozyonu\n"
            "                      azaltmak               mitigate erosion.                hafifletmeye yardımcı olur.\n"
            "  2   ascertain       tespit etmek,          Investigators tried to           Müfettişler yangının nedenini\n"
            "                      belirlemek             ascertain the cause of fire.     tespit etmeye çalıştı.\n"
            "\f"
            "                               Sayfa 2\n"
            "No    Kelime          Anlamı                 Örnek                            Çeviri\n"
            "  3   bolster         güçlendirmek           Fresh data will bolster          Yeni veriler savımızı\n"
            "                                             our argument.                    güçlendirecek.\n"
        )
        rows = parse_pdftotext_layout(layout_text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].word, "mitigate")
        self.assertEqual(rows[0].meaning, "hafifletmek, azaltmak")
        self.assertEqual(rows[0].example, "Soil conservation helps mitigate erosion.")
        self.assertEqual(rows[0].translation, "Toprak koruma erozyonu hafifletmeye yardımcı olur.")
        self.assertEqual(rows[1].word, "ascertain")
        self.assertEqual(rows[2].word, "bolster")
        self.assertEqual(rows[2].example, "Fresh data will bolster our argument.")

    def test_free_form_lists_docx_odt_and_ai_fallback_import(self) -> None:
        import zipfile
        from backend.lexis_cli import ai_parse_lines, parse_vocab_text, read_text_import

        rows, unparsed = parse_vocab_text(
            "A2 Kelime Listesi\n"
            "1. apple - elma\n"
            "2) book = kitap\n"
            "• run: koşmak\n"
            "constant (adj): sürekli, sabit\n"
            "take off (pv) kalkmak\n"
            "word\tmeaning\texample\ttranslation\n"
            "borrow\tödünç almak\tCan I borrow it?\tÖdünç alabilir miyim?\n"
            "house | ev\n"
            "Sayfa 1\n"
            "Bu satır bir açıklamadır ve kelime değildir çünkü uzun\n"
        )
        got = [(r.word, r.meaning, r.pos) for r in rows]
        self.assertEqual(
            got,
            [
                ("apple", "elma", ""),
                ("book", "kitap", ""),
                ("run", "koşmak", ""),
                ("constant", "sürekli, sabit", "adjective"),
                ("take off", "kalkmak", "verb"),
                ("borrow", "ödünç almak", ""),
                ("house", "ev", ""),
            ],
        )
        self.assertEqual(rows[5].example, "Can I borrow it?")
        self.assertEqual(unparsed, ["A2 Kelime Listesi", "Bu satır bir açıklamadır ve kelime değildir çünkü uzun"])

        w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        docx = Path(self.tmp.name, "liste.docx")
        with zipfile.ZipFile(docx, "w") as zf:
            zf.writestr(
                "word/document.xml",
                f"<w:document {w}><w:body>"
                "<w:p><w:r><w:t>Unit 1</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>dizzy (adj): başı dönen</w:t></w:r></w:p>"
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Word</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>Meaning</w:t></w:r></w:p></w:tc></w:tr>"
                "<w:tr><w:tc><w:p><w:r><w:t>lake</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>göl</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                "</w:body></w:document>",
            )
        rows, unparsed = read_text_import(docx)
        self.assertEqual([(r.word, r.meaning) for r in rows], [("dizzy", "başı dönen"), ("lake", "göl")])
        self.assertEqual(unparsed, ["Unit 1"])

        odt = Path(self.tmp.name, "liste.odt")
        with zipfile.ZipFile(odt, "w") as zf:
            zf.writestr(
                "content.xml",
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
                'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"><office:body><office:text>'
                "<text:p>fridge = buzdolabı</text:p>"
                "<table:table><table:table-row><table:table-cell><text:p>plate</text:p></table:table-cell>"
                "<table:table-cell><text:p>tabak</text:p></table:table-cell></table:table-row></table:table>"
                "</office:text></office:body></office:document-content>",
            )
        rows, _ = read_text_import(odt)
        self.assertEqual([(r.word, r.meaning) for r in rows], [("fridge", "buzdolabı"), ("plate", "tabak")])

        # Önizleme tüm satırları döner; onay önizlemedeki satırları (AI dahil) aynen ekler.
        prev = self.rpc("preview-import", {"path": str(docx)})
        self.assertEqual((prev["kind"], prev["total"], prev["unparsed"], prev["duplicates"]), ("docx", 2, 1, 0))
        extra = prev["rows"] + [{"word": "genius", "meaning": "deha"}]
        res = self.rpc("confirm-import", {"path": str(docx), "listName": "A1", "rows": extra})
        self.assertEqual((res["added"], res["total"]), (3, 3))
        self.assertEqual(len(res["enrichIds"]), 3)  # örneksiz kelimeler arka planda zenginleşecek
        self.assertEqual(self.rpc("preview-import", {"path": str(docx)})["duplicates"], 2)
        words = {w["word"]: w for w in self.rpc("list-words", {"name": "A1"})["words"]}
        self.assertEqual(words["dizzy"]["meaning"], "başı dönen")

        calls = []

        def fake_runner(argv, **kw):
            calls.append(argv)
            out = {"is_error": False, "structured_output": {"rows": [
                {"word": "curiosity", "meaning": "merak", "example": "", "translation": ""},
                {"word": "", "meaning": "boş kelime atılır", "example": "", "translation": ""},
            ]}}
            return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")

        settings = {"aiProvider": "claude", "targetLang": "English", "meaningLang": "Turkish"}
        ai_rows, consumed = ai_parse_lines(["curiosity -> merak"] * 31, settings, runner=fake_runner)
        self.assertEqual(len(calls), 2)  # 30'luk parçalar
        self.assertEqual(consumed, 31)
        self.assertEqual([(r.word, r.meaning) for r in ai_rows], [("curiosity", "merak")] * 2)

        def broken_runner(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, "", "quota")

        # AI başarısızsa satırlar tüketilmiş sayılmaz, önizlemede yeniden denenebilir kalır.
        self.assertEqual(ai_parse_lines(["x y z"] * 5, settings, runner=broken_runner), ([], 0))

    def test_free_form_parser_edge_cases(self) -> None:
        from unittest import mock
        from backend import lexis_cli
        from backend.lexis_cli import parse_vocab_line, read_text_import, word_key

        cases = {
            "color\trenk (US)\tColor of the sky": ("color", "renk (US)", "Color of the sky"),
            "fall - sonbahar (US), düşmek": ("fall", "sonbahar (US), düşmek", ""),
            "1\tapple\telma": ("apple", "elma", ""),
            "| 1 | apple | elma |": ("apple", "elma", ""),
            "- **apple** - elma": ("apple", "elma", ""),
            "run - koşmak (örn: hızlı)": ("run", "koşmak (örn: hızlı)", ""),
            "dizzy (adj)   başı dönen": ("dizzy", "başı dönen", ""),
        }
        for line, want in cases.items():
            row = parse_vocab_line(line)
            self.assertIsNotNone(row, line)
            self.assertEqual((row.word, row.meaning, row.example), want, line)
        self.assertEqual(parse_vocab_line("dizzy (adj)   başı dönen").pos, "adjective")
        for heading in ("Unit 1 - Food and drink", "## Unit 1: Greetings", "| Word | Meaning |"):
            self.assertIsNone(parse_vocab_line(heading), heading)
        self.assertEqual(word_key("  Island  Hopping "), "island hopping")

        # PDF'te tek numaralı içindekiler satırı tablo çözücüyü tetiklese de serbest satırlar kaybolmaz.
        pdf = Path(self.tmp.name, "toc.pdf")
        pdf.write_bytes(b"%PDF-1.4")
        toc = "1   Contents   3\nconstant (adj): sabit\ndizzy (adj): başı dönen\n"
        with mock.patch.object(lexis_cli, "extract_text", return_value=toc):
            rows, _ = read_text_import(pdf)
        self.assertEqual([r.word for r in rows], ["constant", "dizzy"])

    def test_legacy_kelime_db_migration_and_csv_export(self) -> None:
        import sqlite3
        import time

        now = time.time()
        legacy_path = Path(self.env["LEXIS_LEGACY_DB"])
        con = sqlite3.connect(str(legacy_path))
        con.executescript(
            """
            CREATE TABLE lists(id INTEGER PRIMARY KEY, name TEXT UNIQUE, enabled INTEGER DEFAULT 1, created_at REAL, source TEXT);
            CREATE TABLE words(id INTEGER PRIMARY KEY, word TEXT UNIQUE, meaning TEXT, pos TEXT, example TEXT,
              translation TEXT, list_id INTEGER, hidden INTEGER DEFAULT 0, enriched INTEGER DEFAULT 1,
              box INTEGER DEFAULT -1, due_at REAL DEFAULT 0, created_at REAL);
            CREATE TABLE events(id INTEGER PRIMARY KEY, word_id INTEGER, ts REAL, qtype TEXT, result TEXT, answer TEXT);
            """
        )
        con.execute("INSERT INTO lists(id, name, enabled, created_at) VALUES(1, 'Eylemler-1', 1, ?)", (now,))
        con.execute(
            "INSERT INTO words(id, word, meaning, pos, example, translation, list_id, hidden, enriched, box, due_at, created_at)"
            " VALUES(1, 'endorse', 'onaylamak, desteklemek', 'verb', 'Boards endorse the plan.', 'Kurullar planı onaylar.', 1, 0, 1, 4, ?, ?)",
            (now + 86400, now - 3600),
        )
        con.execute(
            "INSERT INTO events(word_id, ts, qtype, result, answer) VALUES(1, ?, 'choice_en_tr', 'correct', 'onaylamak')",
            (now - 60,),
        )
        con.commit()
        con.close()

        snap0 = self.rpc("snapshot")
        self.assertTrue(snap0["legacyAvailable"])

        mig = self.rpc("import-legacy")
        self.assertTrue(mig["ok"])
        self.assertEqual(mig["addedWords"], 1)
        self.assertEqual(mig["stats"]["settled"], 1)
        self.assertEqual(mig["stats"]["byType"].get("choice_word_meaning"), 100)
        self.assertEqual(mig["words"][0]["box"], 4)

        # Idempotent second run
        mig2 = self.rpc("import-legacy")
        self.assertEqual(mig2["addedWords"], 0)

        out_csv = Path(self.tmp.name) / "exported.csv"
        exp = self.rpc("export-csv", {"path": str(out_csv)})
        self.assertTrue(exp["ok"])
        self.assertEqual(exp["count"], 1)
        self.assertIn("endorse", out_csv.read_text(encoding="utf-8"))

    def test_hybrid_free_dictionary_ai_fallback_custom_v1_and_dirty_edit_guard(self) -> None:
        import http.server
        import stat
        import threading
        import urllib.parse

        counters = {"wikt": 0, "tatoeba": 0, "mymemory": 0, "v1_models": 0, "v1_chat": 0, "last_auth": "", "last_prompt": ""}

        class MockHybridHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # noqa: ANN001
                return

            def _send_json(self, obj: dict, code: int = 200) -> None:
                raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                if parsed.path.startswith("/wikt/entries/"):
                    counters["wikt"] += 1
                    parts = parsed.path.strip("/").split("/")
                    word = urllib.parse.unquote(parts[-1])
                    if word == "mitigate":
                        self._send_json(
                            {
                                "word": "mitigate",
                                "entries": [
                                    {
                                        "partOfSpeech": "verb",
                                        "senses": [
                                            {
                                                "definition": "To reduce, lessen, or decrease",
                                                "examples": ["Trees mitigate heat islands."],
                                                "translations": [
                                                    {"language": {"code": "tr"}, "word": "hafifletmek"},
                                                    {"language": {"code": "tr"}, "word": "azaltmak"},
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        )
                    else:
                        self._send_json({"word": word, "entries": []})
                elif parsed.path == "/tatoeba/search":
                    counters["tatoeba"] += 1
                    q = (qs.get("query") or [""])[0]
                    if q == "mitigate":
                        self._send_json(
                            {
                                "results": [
                                    {
                                        "text": "Good insulation can mitigate winter heat loss.",
                                        "translations": [[{"text": "İyi yalıtım kışın ısı kaybını hafifletebilir."}]],
                                    }
                                ]
                            }
                        )
                    else:
                        self._send_json({"results": []})
                elif parsed.path == "/mymemory/get":
                    counters["mymemory"] += 1
                    q = (qs.get("q") or [""])[0]
                    pair = (qs.get("langpair") or [""])[0]
                    if q.lower() == "hello" and pair == "en|tr":
                        self._send_json({"responseData": {"translatedText": "merhaba"}})
                    else:
                        self._send_json({"responseData": {"translatedText": ""}})
                elif parsed.path == "/v1/models":
                    counters["v1_models"] += 1
                    counters["last_auth"] = self.headers.get("Authorization", "")
                    self._send_json({"data": [{"id": "qwen2.5:3b"}, {"id": "llama3.2:3b"}]})
                else:
                    self._send_json({"error": "not found"}, 404)

            def do_POST(self) -> None:
                if self.path == "/v1/chat/completions":
                    counters["v1_chat"] += 1
                    counters["last_auth"] = self.headers.get("Authorization", "")
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    prompt = body["messages"][-1]["content"]
                    counters["last_prompt"] = prompt
                    if '"accept"' in prompt or "accept" in prompt.lower():
                        content = "```json\n{\"accept\": true}\n```"
                    elif "source" in prompt and "translation" in prompt:
                        content = "```json\n{\"translation\": \"merhaba dünya\", \"source\": \"target\"}\n```"
                    else:
                        content = (
                            "```json\n"
                            "{\"meaning\": \"göz ardı etmek\", \"pos\": \"verb\","
                            " \"example\": \"Do not brush aside safety warnings.\","
                            " \"translation\": \"Güvenlik uyarılarını göz ardı etme.\"}\n"
                            "```"
                        )
                    self._send_json({"choices": [{"message": {"content": content}}]})
                else:
                    self._send_json({"error": "not found"}, 404)

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockHybridHandler)
        port = srv.server_address[1]
        thr = threading.Thread(target=srv.serve_forever, daemon=True)
        thr.start()
        try:
            self.env["LEXIS_WIKTIONARY_URL"] = f"http://127.0.0.1:{port}/wikt/entries"
            self.env["LEXIS_TATOEBA_URL"] = f"http://127.0.0.1:{port}/tatoeba/search"
            self.env["LEXIS_MYMEMORY_URL"] = f"http://127.0.0.1:{port}/mymemory/get"

            # Save 0600 custom API key and verify it is NOT in settings.json
            saved_key = self.rpc("save-api-key", {"apiKey": "sk-local-secret-123"})
            self.assertTrue(saved_key["hasCustomApiKey"])
            key_file = Path(self.env["LEXIS_STATE_DIR"]) / "api_key"
            self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
            self.rpc(
                "save-settings",
                {
                    "aiProvider": "custom",
                    "customBaseUrl": f"http://127.0.0.1:{port}/v1",
                    "customModel": "qwen2.5:3b",
                    "targetLang": "English",
                    "meaningLang": "Turkish",
                },
            )
            cfg_txt = Path(self.env["LEXIS_CONFIG"]).read_text(encoding="utf-8")
            self.assertNotIn("sk-local-secret-123", cfg_txt)

            # Fetch models from /v1/models
            models_res = self.rpc("fetch-custom-models", {"baseUrl": f"http://127.0.0.1:{port}/v1"})
            self.assertEqual(models_res["models"], ["qwen2.5:3b", "llama3.2:3b"])
            self.assertEqual(counters["last_auth"], "Bearer sk-local-secret-123")

            # (a) Complete Free Dictionary hit ('mitigate') -> zero AI chat calls!
            w_dict = self.rpc("add-word", {"word": "mitigate"})["wordId"]
            enr1 = self.rpc("enrich-word", {"wordId": w_dict})
            self.assertTrue(enr1["enriched"])
            self.assertEqual(enr1["via"], "dictionary")
            self.assertEqual(counters["v1_chat"], 0)
            self.assertIn("hafifletmek", enr1["word"]["meaning"])
            self.assertIn("mitigate", enr1["word"]["example"])

            # (b) Idiom missing from dictionary ('brush aside') -> falls back to Custom /v1 AI & strips ```json fences
            w_idiom = self.rpc("add-word", {"word": "brush aside"})["wordId"]
            enr2 = self.rpc("enrich-word", {"wordId": w_idiom})
            self.assertTrue(enr2["enriched"])
            self.assertEqual(enr2["via"], "ai")
            self.assertEqual(counters["v1_chat"], 1)
            self.assertIn("English", counters["last_prompt"])
            self.assertIn("Turkish", counters["last_prompt"])
            self.assertEqual(enr2["word"]["meaning"], "göz ardı etmek")

            # (c) Dirty-edit guard: if user manually wrote an example while meaning was still empty,
            # enrichment fills meaning but keeps user's example and does NOT attach AI's mismatched translation
            w_dirty = self.rpc(
                "add-word",
                {"word": "brush aside II", "example": "My custom example sentence."},
            )["wordId"]
            enr_dirty = self.rpc("enrich-word", {"wordId": w_dirty})
            self.assertEqual(enr_dirty["word"]["meaning"], "göz ardı etmek")
            self.assertEqual(enr_dirty["word"]["example"], "My custom example sentence.")
            self.assertEqual(enr_dirty["word"]["translation"], "")

            # If user manually filled meaning before enrich-word runs, enrich-word does not overwrite meaning
            w_manual = self.rpc("add-word", {"word": "untouched"})["wordId"]
            self.rpc("update-word", {"wordId": w_manual, "meaning": "elle yazılan anlam"})
            chat_before = counters["v1_chat"]
            enr_manual = self.rpc("enrich-word", {"wordId": w_manual})
            self.assertEqual(enr_manual["word"]["meaning"], "elle yazılan anlam")
            self.assertEqual(counters["v1_chat"], chat_before)

            # (d) AI judge-answer via Custom /v1
            self.rpc("grade-question", {"wordId": w_idiom, "qtype": "intro", "action": "intro", "now": 100.0})
            judged = self.rpc(
                "judge-answer",
                {"wordId": w_idiom, "qtype": "type_word_meaning", "typedText": "önemsememek", "now": 800.0},
            )
            self.assertEqual(judged["result"], "correct")

            # (e) Translate with AI enabled vs AI off (Free Dictionary + MyMemory)
            tr_ai = self.rpc("translate-text", {"text": "hello world"})
            self.assertEqual(tr_ai["translation"], "merhaba dünya")
            self.assertEqual(tr_ai["via"], "ai")
            self.assertEqual(tr_ai["candidateWord"], "hello world")

            self.rpc("save-settings", {"aiProvider": "off"})
            tr_free = self.rpc("translate-text", {"text": "hello"})
            self.assertEqual(tr_free["translation"], "merhaba")
            self.assertEqual(tr_free["via"], "dictionary")
            self.assertEqual(tr_free["candidateWord"], "hello")

            # Clear API key removes file
            cleared = self.rpc("clear-api-key")
            self.assertFalse(cleared["hasCustomApiKey"])
            self.assertFalse(key_file.exists())

            # (f) CLI model flags & mise PATH discovery
            from backend.lexis_cli import build_cli_command, child_env

            self.assertIn(".local/share/mise/shims", child_env()["PATH"])
            agy_cmd = build_cli_command("agy", "test prompt", {"type": "object"}, "/tmp")
            self.assertIn("gemini-3.8-flash-low", agy_cmd)
            claude_cmd = build_cli_command("claude", "test prompt", {"type": "object"}, "/tmp")
            self.assertIn("claude-haiku-5-5", claude_cmd)
            self.assertIn("--no-session-persistence", claude_cmd)
            codex_cmd = build_cli_command("codex", "test prompt", {"type": "object"}, self.tmp.name)
            self.assertIn("gpt-5.6-luna", codex_cmd)
            self.assertIn("read-only", codex_cmd)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_marketplace_manifest_qml_and_security_baseline(self) -> None:
        import re

        required_files = [
            "manifest.json",
            "LICENSE",
            "SECURITY.md",
            "README.md",
            "README.tr.md",
            "preview.png",
        ]
        for rel in required_files:
            self.assertTrue((ROOT / rel).is_file(), f"Missing required file: {rel}")

        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("schemaVersion"), 1)
        self.assertEqual(manifest.get("id"), "io.github.fatihaydost.lexis")
        self.assertEqual(manifest.get("name"), "Lexis")
        entry_points = manifest.get("entryPoints") or {}
        for ep_key in ("service", "barWidget"):
            ep_rel = entry_points.get(ep_key)
            self.assertTrue(ep_rel and (ROOT / ep_rel).is_file(), f"Missing entryPoint {ep_key}")

        preview_file = ROOT / "preview.png"
        preview_bytes = preview_file.read_bytes()
        self.assertTrue(preview_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "preview.png is not a valid PNG")
        self.assertLess(len(preview_bytes), 250 * 1024, "preview.png must be < 250 KiB")

        # Marketplace kurulumu git'ten gelir: doğrulama ve taramalar yalnız git'in taşıyacağı dosyalarda
        # (media/node_modules, out/ ve kayıt klipleri .gitignore ile dışarıda).
        shipped = [
            ROOT / rel
            for rel in subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            if (ROOT / rel).exists() or (ROOT / rel).is_symlink()
        ]
        ship_dir = Path(self.tmp.name) / "io.github.fatihaydost.lexis"
        for src in shipped:
            dst = ship_dir / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_symlink():
                dst.symlink_to(os.readlink(src))
            else:
                dst.write_bytes(src.read_bytes())

        # Validate via omarchy CLI
        val_proc = subprocess.run(
            ["omarchy", "plugin", "validate", str(ship_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(val_proc.returncode, 0, f"omarchy plugin validate failed: {val_proc.stdout} {val_proc.stderr}")

        # Walk repo files and enforce Marketplace security & hygiene rules
        forbidden_name_re = re.compile(r"(install|installer|setup|uninstall)", re.IGNORECASE)
        forbidden_cmd_re = re.compile(
            r"(\bsudo\b|\bpkexec\b|\bsystemctl\b|\bsystemd-run\b|\bpacman\s+-S\b|\bapt-get\b|curl\b[^\n]*\|\s*(?:ba)?sh\b)"
        )
        fractional_px_re = re.compile(r"pixelSize\s*:\s*\d+\.\d+")

        qml_files: list[str] = []
        for path in sorted(shipped):
            rel_parts = path.relative_to(ROOT).parts
            if any(p in (".git", ".superpowers", "__pycache__") for p in rel_parts):
                continue
            self.assertFalse(path.is_symlink(), f"Symlinks are forbidden in Marketplace plugins: {path}")
            if path.is_dir():
                continue

            self.assertIsNone(
                forbidden_name_re.search(path.name),
                f"Forbidden installer-like filename in repo: {path.name}",
            )
            st = path.stat()
            self.assertEqual(st.st_mode & 0o111, 0, f"Executable bit forbidden on plugin file: {path}")
            if path.suffix in (".qml", ".js", ".py", ".md", ".json", ".sh", ".csv"):
                self.assertLess(st.st_size, 512 * 1024, f"File exceeds 512 KiB scan limit: {path}")

            if path.suffix == ".qml":
                qml_files.append(str(path.relative_to(ROOT)))
                qml_txt = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    fractional_px_re.search(qml_txt),
                    f"Fractional font.pixelSize in {path}",
                )

            if path.resolve() != Path(__file__).resolve() and path.suffix in (
                ".py",
                ".qml",
                ".js",
                ".json",
                ".md",
                ".csv",
            ):
                txt = path.read_text(encoding="utf-8")
                m = forbidden_cmd_re.search(txt)
                self.assertIsNone(m, f"Forbidden privileged/package pattern {m.group(0) if m else ''} in {path}")

        self.assertGreaterEqual(len(qml_files), 12)
        lint_proc = subprocess.run(
            [
                "/usr/lib/qt6/bin/qmllint",
                "--bare",
                "-I",
                "/usr/lib/qt6/qml",
                "-I",
                "/usr/share/omarchy/shell",
                "--unqualified",
                "disable",
                "--import",
                "disable",
                "--unresolved-type",
                "disable",
                "--uncreatable-type",
                "disable",
                *qml_files,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(lint_proc.returncode, 0, f"qmllint failed: {lint_proc.stdout}\n{lint_proc.stderr}")
        self.assertEqual(lint_proc.stdout.strip(), "", f"qmllint stdout not empty: {lint_proc.stdout}")
        self.assertEqual(lint_proc.stderr.strip(), "", f"qmllint stderr not empty: {lint_proc.stderr}")

    def test_short_word_root_swap_guard(self) -> None:
        from backend.lexis_cli import match_answer

        # Distinct 5-6 letter Turkish verbs sharing -mak/-mek must NOT match via 1-char edit distance
        self.assertFalse(match_answer("almak", "kalmak"))
        self.assertFalse(match_answer("almak", "salmak"))
        self.assertFalse(match_answer("atmak", "batmak"))
        self.assertFalse(match_answer("satmak", "atmak"))
        self.assertFalse(match_answer("make", "take"))
        # Genuine mid/ending typo with matching initial character still matches on >=6 char meanings
        self.assertTrue(match_answer("kalmk", "kalmak"))
        self.assertTrue(match_answer("hafifletmk", "hafifletmek"))

    def test_distractors_do_not_overlap_each_other(self) -> None:
        # Target 'fragile' + 3 candidates where 'swift' and 'rapid' share normalized token 'cabuk'
        w_target = self.rpc("add-word", {"word": "fragile", "meaning": "kırılgan", "pos": "adjective"})["wordId"]
        w_swift = self.rpc("add-word", {"word": "swift", "meaning": "hızlı, çabuk", "pos": "adjective"})["wordId"]
        w_rapid = self.rpc("add-word", {"word": "rapid", "meaning": "çabuk, seri", "pos": "adjective"})["wordId"]
        w_opaque = self.rpc("add-word", {"word": "opaque", "meaning": "mat", "pos": "adjective"})["wordId"]
        for wid in (w_target, w_swift, w_rapid, w_opaque):
            self.rpc("grade-question", {"wordId": wid, "qtype": "intro", "action": "intro", "now": 100.0})

        # Only 2 mutually non-overlapping distractors exist -> must fall back to typed instead of picking both swift & rapid
        q_only_two = self.rpc("next-question", {"wordId": w_target, "now": 800.0})["question"]
        self.assertEqual(q_only_two["qtype"], "type_word_meaning")

        # Once a 3rd distinct distractor is added, 4-choice works and never includes both swift/hızlı and rapid/çabuk together
        w_dense = self.rpc("add-word", {"word": "dense", "meaning": "yoğun", "pos": "adjective"})["wordId"]
        self.rpc("grade-question", {"wordId": w_dense, "qtype": "intro", "action": "intro", "now": 100.0})
        for i in range(20):
            q = self.rpc("next-question", {"wordId": w_target, "now": 900.0 + i, "seed": i})["question"]
            self.assertIn(q["qtype"], ("choice_word_meaning", "choice_meaning_word"))
            self.assertEqual(len(q["choices"]), 4)
            choices_set = set(q["choices"])
            self.assertFalse({"swift", "rapid"}.issubset(choices_set))
            self.assertFalse({"hızlı", "çabuk"}.issubset(choices_set))

    def test_scheduled_timer_defers_replacement_while_user_typing_or_judging(self) -> None:
        bridge_url = (ROOT / "Bridge.js").as_uri()
        qml_test = Path(self.tmp.name) / "tst_quiz_tick.qml"
        qml_test.write_text(
            f"""import QtQuick
import QtTest
import "{bridge_url}" as Bridge

TestCase {{
  name: "QuizTickDeferTests"

  function test_defers_when_input_active_or_judging() {{
    compare(typeof Bridge.decideQuizTick, "function")
    var dTyping = Bridge.decideQuizTick(1500, 1000, 300, 0, false, true, true, false)
    compare(dTyping.action, "defer_typing")
    compare(dTyping.nextLastEpoch, 1230)

    var dJudging = Bridge.decideQuizTick(1500, 1000, 300, 0, false, true, false, true)
    compare(dJudging.action, "defer_typing")
    compare(dJudging.nextLastEpoch, 1230)

    var dIdleCard = Bridge.decideQuizTick(1500, 1000, 300, 0, false, true, false, false)
    compare(dIdleCard.action, "draw")
  }}
}}
""",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        proc = subprocess.run(
            ["/usr/lib/qt6/bin/qmltestrunner", "-input", str(qml_test)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"qmltestrunner failed:\n{proc.stdout}\n{proc.stderr}")

        svc_txt = (ROOT / "Service.qml").read_text(encoding="utf-8")
        self.assertIn("Bridge.decideQuizTick(", svc_txt)
        self.assertIn("toastWin.inputActive", svc_txt)
        self.assertIn("svcRoot.judging", svc_txt)

    def test_pages_do_not_overflow_columns_in_en_or_tr(self) -> None:
        mock_imports = Path(self.tmp.name) / "qml_imports"
        (mock_imports / "qs" / "Commons").mkdir(parents=True, exist_ok=True)
        (mock_imports / "qs" / "Commons" / "qmldir").write_text(
            "module qs.Commons\nsingleton Style 1.0 Style.qml\n",
            encoding="utf-8",
        )
        (mock_imports / "qs" / "Commons" / "Style.qml").write_text(
            'pragma Singleton\nimport QtQuick\nQtObject {\n'
            '  readonly property QtObject font: QtObject { readonly property string family: "Monospace" }\n'
            '}\n',
            encoding="utf-8",
        )
        (mock_imports / "Quickshell").mkdir(parents=True, exist_ok=True)
        (mock_imports / "Quickshell" / "qmldir").write_text(
            "module Quickshell\nsingleton Quickshell 1.0 Quickshell.qml\n",
            encoding="utf-8",
        )
        (mock_imports / "Quickshell" / "Quickshell.qml").write_text(
            'pragma Singleton\nimport QtQuick\nQtObject {\n'
            '  readonly property var screens: [{ name: "eDP-1" }, { name: "DP-1" }]\n'
            '}\n',
            encoding="utf-8",
        )

        pages_uri = (ROOT / "pages").as_uri()
        qml_test = Path(self.tmp.name) / "tst_layout_overflow.qml"
        qml_test.write_text(
            f"""import QtQuick
import QtTest
import "{pages_uri}"

Item {{
  id: harness
  width: 830
  height: 680

  QtObject {{
    id: mockSvc
    property string lang: "en"
    property var tokens: ({{}})
    property bool isMuted: false
    property int nextInSeconds: 245
    property var todayData: ({{ answered: 0, goal: 50, totalWords: 0, recent: [] }})
    property var wordsData: [
      {{ id: 1, word: "mitigate", meaning: "hafifletmek, azaltmak", last5: ["correct", "wrong"] }}
    ]
    property var listsData: [
      {{ name: "Academic Starter Deck", count: 30, enabled: true, hasSource: true, source: "/tmp/starter.csv" }}
    ]
    property var selectedWord: ({{
      id: 1,
      word: "mitigate",
      meaning: "hafifletmek, azaltmak",
      pos: "verb",
      box: 2,
      hidden: true,
      listName: "Academic Starter Deck",
      example: "Trees mitigate urban heat.",
      exampleHtml: "Trees <b>mitigate</b> urban heat.",
      translation: "Ağaçlar kentsel ısıyı hafifletir.",
      history: ["correct", "wrong", "correct"]
    }})
    property string wordsListFilter: "Academic Starter Deck"
    property bool translating: false
    property var lastTranslation: ({{
      text: "supercalifragilisticexpialidocious phrase",
      translation: "çok uzun örnek çeviri metni",
      source: "target",
      via: "dictionary",
      candidateWord: "supercalifragilisticexpialidocious phrase example"
    }})
    property var statsData: ({{
      answeredToday: 12,
      accuracy: 84,
      settled: 5,
      totalWords: 30,
      days: [0,1,2,3,4,5,0,1,2,3,4,5,0,1,2,3,4,5,0,1,2,3,4,5,0,1,2,3,4,8],
      hardest: [{{ id: 1, word: "mitigate", misses: 4 }}, {{ id: 2, word: "scrutinize", misses: 2 }}],
      byType: ({{ choice_word_meaning: 90, choice_meaning_word: 80, type_word_meaning: 75, type_context: 70 }})
    }})
    property var settings: ({{
      language: lang,
      toastScreen: "",
      intervalMin: 5,
      dailyGoal: 50,
      targetLang: "English",
      meaningLang: "Turkish",
      dictionaryEnabled: true,
      aiProvider: "custom",
      customBaseUrl: "http://127.0.0.1:11434/v1",
      customModel: "qwen2.5:7b"
    }})
    property var providers: [
      {{ id: "agy", installed: true, model: "gemini-3.8-flash-low" }}
    ]
    property var customModels: ["qwen2.5:7b", "llama3.2:3b-instruct-q4_K_M"]
    property bool hasCustomApiKey: true
    property bool legacyAvailable: true
    property string aiTestStatus: "Connected to http://127.0.0.1:11434/v1 (qwen2.5:7b)"
    property string statusNotice: "Imported 142 words from legacy Kelime database"
    property string dbPath: "/home/user/.local/share/lexis/lexis.sqlite"
  }}

  TodayPage {{ id: todayPage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}
  WordsPage {{ id: wordsPage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}
  TranslatePage {{ id: translatePage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}
  StatsPage {{ id: statsPage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}
  ListsPage {{ id: listsPage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}
  SettingsPage {{ id: settingsPage; anchors.fill: parent; service: mockSvc; fontFamily: "Monospace" }}

  TestCase {{
    name: "PageLayoutOverflowTests"
    when: windowShown

    function collectIssues(node, pageName, issues) {{
      if (!node || !node.visible || node.opacity <= 0) return
      var kids = node.children || []
      var isFlickableContent = !!(node.parent && node.parent.contentItem === node)
      // 1) Check children overflowing any explicit-width parent container (unless parent clips scrollable content)
      if (node.width > 0 && !node.clip && node.contentItem === undefined) {{
        for (var i = 0; i < kids.length; i++) {{
          var ch = kids[i]
          if (!ch || !ch.visible || ch.opacity <= 0 || ch.width <= 0 || ch.height <= 0) continue
          if (isFlickableContent && String(ch).indexOf("QQuickItem") === 0 && (!ch.children || ch.children.length === 0)) continue
          if (ch.x + ch.width > node.width + 1.5) {{
            issues.push(pageName + ": child (" + Math.round(ch.x) + "+" + Math.round(ch.width) + "=" + Math.round(ch.x + ch.width)
              + ") overflows parent width " + Math.round(node.width)
              + (ch.text !== undefined ? (" text='" + ch.text + "'") : ""))
          }}
        }}
      }}
      // 2) Check unclipped Text inside a button/badge Rectangle overflowing its parent Rectangle
      if (node.text !== undefined && node.parent && node.parent.width > 0 && !node.parent.clip && node.elide === Text.ElideNone && node.wrapMode === Text.NoWrap) {{
        if (node.implicitWidth > node.parent.width + 1.5) {{
          issues.push(pageName + ": Text '" + node.text + "' implicitWidth " + Math.round(node.implicitWidth)
            + " > parent width " + Math.round(node.parent.width))
        }}
      }}
      // 3) Check sibling horizontal overlap inside non-Row/Flow/Column Item headers (left vs right anchored blocks)
      var cls = String(node)
      if (!isFlickableContent && cls.indexOf("QQuickItem") === 0 && kids.length === 2) {{
        var a = kids[0], b = kids[1]
        var aIsArea = String(a).indexOf("QQuickMouseArea") === 0
        var bIsArea = String(b).indexOf("QQuickMouseArea") === 0
        if (!aIsArea && !bIsArea && a && b && a.visible && b.visible && a.width > 0 && b.width > 0 && a.height > 0 && b.height > 0) {{
          var leftItem = a.x <= b.x ? a : b
          var rightItem = a.x <= b.x ? b : a
          var vOverlap = Math.min(leftItem.y + leftItem.height, rightItem.y + rightItem.height) - Math.max(leftItem.y, rightItem.y)
          if (vOverlap > 2 && (leftItem.x + leftItem.width) > (rightItem.x - 2)) {{
            issues.push(pageName + ": header siblings overlap (" + Math.round(leftItem.x + leftItem.width)
              + " > " + Math.round(rightItem.x) + ")")
          }}
        }}
      }}
      for (var j = 0; j < kids.length; j++) {{
        collectIssues(kids[j], pageName, issues)
      }}
    }}

    function test_no_horizontal_overflow_across_pages_and_languages() {{
      var combos = [
        {{ w: 830, h: 680, lang: "en" }},
        {{ w: 830, h: 680, lang: "tr" }},
        {{ w: 550, h: 520, lang: "en" }},
        {{ w: 550, h: 520, lang: "tr" }}
      ]
      var allIssues = []
      var pages = [
        ["TodayPage", todayPage],
        ["WordsPage", wordsPage],
        ["TranslatePage", translatePage],
        ["StatsPage", statsPage],
        ["ListsPage", listsPage],
        ["SettingsPage", settingsPage]
      ]
      for (var c = 0; c < combos.length; c++) {{
        var cb = combos[c]
        harness.width = cb.w
        harness.height = cb.h
        mockSvc.lang = cb.lang
        mockSvc.todayData = ({{ answered: 0, goal: 50, totalWords: 0, recent: [] }})
        wordsPage.formMode = ""
        listsPage.previewData = null
        listsPage.inspectedListName = ""
        listsPage.pathEntryOpen = true  // zenity yokken açılan yol kutusu da taşmamalı
        mockSvc.settings = {{
          language: cb.lang,
          toastScreen: "",
          intervalMin: 5,
          dailyGoal: 50,
          targetLang: "English",
          meaningLang: "Turkish",
          dictionaryEnabled: true,
          aiProvider: "custom",
          customBaseUrl: "http://127.0.0.1:11434/v1",
          customModel: "qwen2.5:7b"
        }}
        wait(10)
        for (var p = 0; p < pages.length; p++) {{
          collectIssues(pages[p][1], pages[p][0] + "[" + cb.lang + "@" + cb.w + "]", allIssues)
        }}

        // Secondary states: Today populated, Words add-form, Lists inspector & CSV preview
        mockSvc.todayData = ({{
          answered: 14,
          goal: 50,
          totalWords: 30,
          recent: [{{ id: 1, word: "mitigate", correct: true, qtype: "choice_word_meaning", ts: "12:04" }}]
        }})
        wordsPage.formMode = "add"
        listsPage.inspectedListName = "Academic Starter Deck (Very Long Custom Deck Title)"
        listsPage.inspectedListSource = "/tmp/starter.csv"
        listsPage.inspectedWords = [{{ id: 1, word: "mitigate", meaning: "hafifletmek, azaltmak", box: 2 }}]
        wait(10)
        collectIssues(todayPage, "TodayPagePopulated[" + cb.lang + "@" + cb.w + "]", allIssues)
        collectIssues(wordsPage, "WordsPageForm[" + cb.lang + "@" + cb.w + "]", allIssues)
        collectIssues(listsPage, "ListsPageInspect[" + cb.lang + "@" + cb.w + "]", allIssues)

        listsPage.previewData = ({{
          kind: "csv",
          total: 120,
          columns: ["word", "meaning", "example", "translation"],
          sampleRow: ["mitigate", "hafifletmek", "Trees mitigate heat.", "Ağaçlar ısıyı hafifletir."],
          rows: [{{ word: "mitigate", meaning: "hafifletmek", example: "Trees mitigate urban heat." }}]
        }})
        wait(10)
        collectIssues(listsPage, "ListsPagePreview[" + cb.lang + "@" + cb.w + "]", allIssues)

        listsPage.previewData = ({{
          kind: "docx",
          total: 29,
          duplicates: 3,
          unparsed: 2,
          unparsedSample: ["A1 Kelime Listesi (Very Long Document Title Line)", "Unit 1 - Food and drink vocabulary"],
          aiAvailable: cb.lang === "en",
          rows: [{{ word: "constant", meaning: "sürekli, sabit", example: "" }}]
        }})
        wait(10)
        collectIssues(listsPage, "ListsPageTextPreview[" + cb.lang + "@" + cb.w + "]", allIssues)
      }}
      verify(allIssues.length === 0, "Layout overflows detected:\\n" + allIssues.join("\\n"))
    }}
  }}
}}
""",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        proc = subprocess.run(
            ["/usr/lib/qt6/bin/qmltestrunner", "-import", str(mock_imports), "-input", str(qml_test)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Layout overflow test failed:\n{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
