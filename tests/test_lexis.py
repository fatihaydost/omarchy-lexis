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


if __name__ == "__main__":
    unittest.main()
