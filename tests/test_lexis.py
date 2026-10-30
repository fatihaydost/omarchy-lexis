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


if __name__ == "__main__":
    unittest.main()
