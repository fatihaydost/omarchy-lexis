from dataclasses import dataclass
import html
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import sys
import time
import unicodedata

# Aralıklı tekrar sabitleri (eski kelime uygulamasıyla birebir aynı)
INTERVALS = [600, 1800, 7200, 86400, 3 * 86400, 7 * 86400]
RETRY = 600
SETTLED_BOX = 4
NEW_PER_DAY = 20
DAY_SEC = 86400

QTYPES = ("type_word_meaning", "type_context", "choice_meaning_word", "choice_word_meaning")
CHOICE_QTYPES = ("choice_meaning_word", "choice_word_meaning")
TYPED_QTYPES = ("type_word_meaning", "type_context")

LEGACY_QTYPE_MAP = {
    "type_en_tr": "type_word_meaning",
    "type_context": "type_context",
    "choice_tr_en": "choice_meaning_word",
    "choice_en_tr": "choice_word_meaning",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE,
  enabled INTEGER DEFAULT 1,
  created_at REAL,
  source TEXT
);
CREATE TABLE IF NOT EXISTS words(
  id INTEGER PRIMARY KEY,
  word TEXT UNIQUE,
  meaning TEXT,
  pos TEXT,
  example TEXT,
  translation TEXT,
  list_id INTEGER,
  hidden INTEGER DEFAULT 0,
  enriched INTEGER DEFAULT 1,
  box INTEGER DEFAULT -1,
  due_at REAL DEFAULT 0,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY,
  word_id INTEGER,
  ts REAL,
  qtype TEXT,
  result TEXT,
  answer TEXT
);
CREATE TABLE IF NOT EXISTS settings(
  key PRIMARY KEY,
  value TEXT
);
CREATE INDEX IF NOT EXISTS events_word ON events(word_id, ts);
"""

WORD_FIELDS = (
    "word",
    "meaning",
    "pos",
    "example",
    "translation",
    "list_id",
    "hidden",
    "enriched",
    "box",
    "due_at",
)

SELECT_WORDS = (
    "SELECT w.id, w.word, w.meaning, w.pos, w.example, w.translation, w.list_id,"
    " w.hidden, w.enriched, w.box, w.due_at, COALESCE(w.created_at, 0), COALESCE(l.name, 'Custom')"
    " FROM words w LEFT JOIN lists l ON l.id = w.list_id"
)
ASKABLE_WHERE = "w.hidden = 0 AND w.meaning != '' AND COALESCE(l.enabled, 1) = 1"

DEFAULT_SETTINGS = {
    "language": "en",
    "themeMode": "omarchy",
    "showProgressInBar": True,
    "toastScreen": "",
    "intervalMin": 5,
    "dailyGoal": 50,
    "targetLang": "English",
    "meaningLang": "Turkish",
    "dictionaryEnabled": True,
    "aiProvider": "off",
    "customBaseUrl": "http://127.0.0.1:11434/v1",
    "customModel": "",
    "mutedUntil": 0.0,
}

CLI_PROVIDERS = {
    "agy": {
        "name": "Gemini (agy)",
        "bin": "agy",
        "login_args": [],
        "model": "gemini-3.8-flash-low",
    },
    "claude": {
        "name": "Claude Code (Haiku)",
        "bin": "claude",
        "login_args": ["auth", "login"],
        "model": "claude-haiku-5-5",
    },
    "codex": {
        "name": "ChatGPT (Codex CLI)",
        "bin": "codex",
        "login_args": ["login"],
        "model": "gpt-5.6-luna",
    },
}

TR_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvwxyz"
_TR_RANK = {c: i for i, c in enumerate(TR_ALPHABET)}
_PUNCT_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SUFFIX_RE = re.compile(r"^(-\w+\s*)+", re.UNICODE)
_MULTI_CHAR_FOLD = (
    ("ß", "ss"),
    ("æ", "ae"),
    ("œ", "oe"),
    ("ø", "o"),
    ("đ", "d"),
    ("ł", "l"),
    ("ı", "i"),
)


def db_path() -> Path:
    env = os.environ.get("LEXIS_DB")
    if env:
        p = Path(env).expanduser()
    else:
        xdg = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
        p = xdg / "lexis" / "lexis.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    env = os.environ.get("LEXIS_CONFIG")
    if env:
        p = Path(env).expanduser()
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        p = xdg / "lexis" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def state_dir() -> Path:
    env = os.environ.get("LEXIS_STATE_DIR")
    if env:
        p = Path(env).expanduser()
    else:
        xdg = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
        p = xdg / "lexis"
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def api_key_path() -> Path:
    return state_dir() / "api_key"


def has_custom_api_key() -> bool:
    p = api_key_path()
    try:
        return p.is_file() and bool(p.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def legacy_db_path() -> Path:
    env = os.environ.get("LEXIS_LEGACY_DB")
    if env:
        return Path(env).expanduser()
    xdg = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return xdg / "kelime" / "kelime.db"


def _user_bin_dirs() -> list[str]:
    h = Path(os.environ.get("HOME") or Path.home())
    return [
        str(h / ".local" / "share" / "mise" / "shims"),
        str(h / ".local" / "share" / "mise" / "installs" / "claude" / "latest"),
        str(h / ".local" / "share" / "mise" / "installs" / "codex" / "latest" / "bin"),
        str(h / ".local" / "bin"),
        str(h / ".npm-global" / "bin"),
        str(h / ".cargo" / "bin"),
        "/usr/local/bin",
    ]


def child_env() -> dict[str, str]:
    parts = [p for p in os.environ.get("PATH", "").split(":") if p]
    for extra in _user_bin_dirs():
        if extra not in parts:
            parts.append(extra)
    return {**os.environ, "PATH": ":".join(parts)}


def find_bin(name: str) -> str | None:
    return shutil.which(name, path=child_env()["PATH"])


def provider_statuses() -> list[dict]:
    out = [
        {"id": "off", "name": "Off (Free Dictionary only)", "installed": True},
    ]
    for pid, meta in CLI_PROVIDERS.items():
        out.append(
            {
                "id": pid,
                "name": meta["name"],
                "installed": find_bin(meta["bin"]) is not None,
                "model": meta["model"],
            }
        )
    out.append({"id": "custom", "name": "Local / Custom (/v1)", "installed": True})
    return out


def ai_can_run(settings: dict) -> bool:
    prov = str(settings.get("aiProvider") or "off")
    if prov == "off":
        return False
    if prov == "custom":
        return bool(str(settings.get("customBaseUrl") or "").strip() and str(settings.get("customModel") or "").strip())
    meta = CLI_PROVIDERS.get(prov)
    return bool(meta and find_bin(meta["bin"]) is not None)


def load_settings() -> dict:
    p = config_path()
    merged = dict(DEFAULT_SETTINGS)
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in DEFAULT_SETTINGS:
                    if k in raw:
                        merged[k] = raw[k]
        except (OSError, ValueError):
            pass
    return _sanitize_settings(merged)


def _sanitize_settings(cfg: dict) -> dict:
    out = dict(DEFAULT_SETTINGS)
    lang = str(cfg.get("language") or "en").lower()
    out["language"] = "tr" if lang == "tr" else "en"
    tmode = str(cfg.get("themeMode") or "omarchy").lower()
    out["themeMode"] = "gruvbox" if tmode == "gruvbox" else "omarchy"
    out["showProgressInBar"] = bool(cfg.get("showProgressInBar", True))
    out["toastScreen"] = str(cfg.get("toastScreen") or "").strip()
    try:
        out["intervalMin"] = max(1, min(60, int(cfg.get("intervalMin", 5))))
    except (TypeError, ValueError):
        out["intervalMin"] = 5
    try:
        out["dailyGoal"] = max(1, min(500, int(cfg.get("dailyGoal", 50))))
    except (TypeError, ValueError):
        out["dailyGoal"] = 50
    out["targetLang"] = str(cfg.get("targetLang") or "English").strip() or "English"
    out["meaningLang"] = str(cfg.get("meaningLang") or "Turkish").strip() or "Turkish"
    out["dictionaryEnabled"] = bool(cfg.get("dictionaryEnabled", True))
    ap = str(cfg.get("aiProvider") or "off").strip().lower()
    out["aiProvider"] = ap if ap in ("off", "agy", "claude", "codex", "custom") else "off"
    out["customBaseUrl"] = str(cfg.get("customBaseUrl") or DEFAULT_SETTINGS["customBaseUrl"]).strip()
    out["customModel"] = str(cfg.get("customModel") or "").strip()
    try:
        out["mutedUntil"] = max(0.0, float(cfg.get("mutedUntil") or 0.0))
    except (TypeError, ValueError):
        out["mutedUntil"] = 0.0
    return out


def save_settings_file(patch: dict) -> dict:
    cur = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in patch:
            cur[k] = patch[k]
    clean = _sanitize_settings(cur)
    p = config_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return clean


def tr_lower(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def tr_sort_key(name: str) -> list:
    return [
        (0, int(part), ())
        if part.isdigit()
        else (1, 0, tuple(_TR_RANK.get(ch, 100 + ord(ch)) for ch in part))
        for part in re.split(r"(\d+)", tr_lower(name))
        if part
    ]


def normalize_token(s: str) -> str:
    s = _PUNCT_RE.sub(" ", tr_lower(s))
    s = " ".join(s.split())
    return _SUFFIX_RE.sub("", s).strip()


def fold_ascii(s: str) -> str:
    base = normalize_token(s)
    for src, dst in _MULTI_CHAR_FOLD:
        base = base.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", base)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    for src, dst in _MULTI_CHAR_FOLD:
        stripped = stripped.replace(src, dst)
    return " ".join(stripped.split()).strip()


def meaning_parts(meaning: str) -> list[str]:
    out = []
    for chunk in re.split(r"[,;/]", meaning or ""):
        norm = normalize_token(chunk)
        if norm:
            out.append(norm)
    return out


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_answer(answer: str, meaning: str) -> bool:
    a = fold_ascii(answer)
    if not a:
        return False
    for raw_part in re.split(r"[,;/]", meaning or ""):
        p = fold_ascii(raw_part)
        if not p:
            continue
        if a == p:
            return True
        if len(a) >= 4 and len(p) >= 5 and _levenshtein(a, p) <= (2 if len(p) >= 10 else 1):
            return True
    return False


def guess_pos(meaning: str) -> str:
    first = (meaning or "").split(",")[0].strip().lower()
    if first.endswith(("mak", "mek")) or first.startswith("to "):
        return "verb"
    return "other"


def choice_label(meaning: str) -> str:
    label = (meaning or "").split(",")[0].strip()
    return label if len(label) <= 28 else label[:27] + "…"


def short_meaning(meaning: str, n: int = 2) -> str:
    return ", ".join(p.strip() for p in (meaning or "").split(",")[:n] if p.strip())


def highlight_word(sentence: str, word: str) -> str:
    if not sentence:
        return ""
    m = re.search(rf"(?i)\b{re.escape(word)}\w*", sentence)
    if not m:
        return html.escape(sentence, quote=False)
    esc = lambda s: html.escape(s, quote=False)  # noqa: E731
    return f"{esc(sentence[:m.start()])}<b>{esc(m.group(0))}</b>{esc(sentence[m.end():])}"


def day_start(now: float) -> float:
    t = time.localtime(now)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


@dataclass
class Word:
    id: int
    word: str
    meaning: str
    pos: str
    example: str
    translation: str
    list_id: int
    hidden: int
    enriched: int
    box: int
    due_at: float
    created_at: float
    list_name: str


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), check_same_thread=False)
        self.con.create_function("tr_lower", 1, lambda s: tr_lower(s or ""), deterministic=True)
        self.con.executescript(SCHEMA)
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(lists)")}
        if "source" not in cols:
            self.con.execute("ALTER TABLE lists ADD COLUMN source TEXT")
            self.con.commit()

    def close(self) -> None:
        self.con.close()

    def _words(self, where: str, args: tuple | list = (), tail: str = "") -> list[Word]:
        rows = self.con.execute(f"{SELECT_WORDS} WHERE {where} {tail}", tuple(args)).fetchall()
        return [Word(*r) for r in rows]

    def ensure_list(self, name: str) -> int:
        clean = (name or "Custom").strip() or "Custom"
        self.con.execute(
            "INSERT OR IGNORE INTO lists(name, created_at) VALUES(?, ?)",
            (clean, time.time()),
        )
        self.con.commit()
        return int(self.con.execute("SELECT id FROM lists WHERE name = ?", (clean,)).fetchone()[0])

    def add_word(
        self,
        word: str,
        meaning: str = "",
        pos: str = "",
        example: str = "",
        translation: str = "",
        list_name: str = "Custom",
        enriched: bool = True,
        box: int = -1,
        due_at: float = 0.0,
        hidden: bool = False,
        created_at: float | None = None,
    ) -> int | None:
        clean_word = " ".join((word or "").strip().lower().split())
        if not clean_word:
            return None
        list_id = self.ensure_list(list_name)
        clean_meaning = (meaning or "").strip()
        resolved_pos = (pos or "").strip() or (guess_pos(clean_meaning) if clean_meaning else "other")
        try:
            cur = self.con.execute(
                "INSERT INTO words(word, meaning, pos, example, translation, list_id, hidden,"
                " enriched, box, due_at, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    clean_word,
                    clean_meaning,
                    resolved_pos,
                    (example or "").strip(),
                    (translation or "").strip(),
                    list_id,
                    int(bool(hidden)),
                    int(bool(enriched)),
                    int(box),
                    float(due_at),
                    time.time() if created_at is None else float(created_at),
                ),
            )
        except sqlite3.IntegrityError:
            return None
        self.con.commit()
        return int(cur.lastrowid)

    def get(self, word_id: int) -> Word | None:
        found = self._words("w.id = ?", (int(word_id),))
        return found[0] if found else None

    def get_by_text(self, word: str) -> Word | None:
        clean_word = " ".join((word or "").strip().lower().split())
        found = self._words("w.word = ?", (clean_word,))
        return found[0] if found else None

    def update_word(self, word_id: int, **fields) -> None:
        bad = set(fields) - set(WORD_FIELDS)
        if bad:
            raise ValueError(f"Unknown word fields: {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.con.execute(f"UPDATE words SET {sets} WHERE id = ?", (*fields.values(), int(word_id)))
        self.con.commit()

    def set_hidden(self, word_id: int, hidden: bool) -> None:
        self.update_word(word_id, hidden=int(bool(hidden)))

    def query_words(self, query: str = "", list_filter: str = "") -> list[Word]:
        if list_filter == "__hidden__":
            where, args = ["w.hidden = 1"], []
        elif list_filter == "__custom__":
            where, args = ["w.hidden = 0", "l.name IN ('Custom', 'Kendi')"], []
        elif list_filter:
            where, args = ["w.hidden = 0", "l.name = ?"], [list_filter]
        else:
            where, args = ["w.hidden = 0"], []

        if query:
            where.append("(tr_lower(w.word) LIKE ? OR tr_lower(w.meaning) LIKE ?)")
            q = f"%{tr_lower(query.strip())}%"
            args.extend([q, q])
        return self._words(" AND ".join(where), args, "ORDER BY tr_lower(w.word), w.id")

    def log_event(
        self,
        word_id: int,
        qtype: str,
        result: str,
        answer: str = "",
        ts: float | None = None,
    ) -> None:
        self.con.execute(
            "INSERT INTO events(word_id, ts, qtype, result, answer) VALUES(?, ?, ?, ?, ?)",
            (int(word_id), time.time() if ts is None else float(ts), qtype, result, answer),
        )
        self.con.commit()

    def last5_map(self, word_ids: list[int]) -> dict[int, list[str]]:
        if not word_ids:
            return {}
        out: dict[int, list[str]] = {wid: [] for wid in word_ids}
        placeholders = ",".join("?" for _ in word_ids)
        rows = self.con.execute(
            f"SELECT word_id, result FROM events"
            f" WHERE word_id IN ({placeholders}) AND result IN ('correct', 'wrong')"
            f" ORDER BY ts ASC, id ASC",
            tuple(word_ids),
        ).fetchall()
        for wid, res in rows:
            out.setdefault(int(wid), []).append(res)
        return {wid: vals[-5:] for wid, vals in out.items()}

    def full_history(self, word_id: int, answered_only: bool = True) -> list[str]:
        extra = " AND result IN ('correct', 'wrong')" if answered_only else ""
        rows = self.con.execute(
            f"SELECT result FROM events WHERE word_id = ?{extra} ORDER BY ts ASC, id ASC",
            (int(word_id),),
        ).fetchall()
        return [r[0] for r in rows]

    def db_setting(self, key: str, default: str = "") -> str:
        row = self.con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_db_setting(self, key: str, value: str) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
            (key, str(value)),
        )
        self.con.commit()

    def due_words(self, now: float) -> list[Word]:
        return self._words(
            f"{ASKABLE_WHERE} AND w.box >= 0 AND w.due_at <= ?",
            (float(now),),
            "ORDER BY w.due_at ASC, w.id ASC",
        )

    def new_words(self, limit: int) -> list[Word]:
        return self._words(
            f"{ASKABLE_WHERE} AND w.box = -1",
            (int(limit),),
            "ORDER BY w.id ASC LIMIT ?",
        )

    def askable(self) -> list[Word]:
        return self._words(ASKABLE_WHERE, (), "ORDER BY w.id ASC")

    def lists_summary(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT l.name, COUNT(w.id), COALESCE(l.enabled, 1), COALESCE(l.source, '')"
            " FROM lists l"
            " LEFT JOIN words w ON w.list_id = l.id AND w.hidden = 0"
            " GROUP BY l.id"
        ).fetchall()
        ordered = sorted(rows, key=lambda r: tr_sort_key(r[0]))
        out = []
        for name, count, enabled, source in ordered:
            src_str = str(source or "")
            has_src = bool(src_str and Path(src_str).is_file())
            out.append(
                {
                    "name": name,
                    "count": int(count),
                    "enabled": bool(enabled),
                    "hasSource": has_src,
                    "source": src_str if has_src else "",
                }
            )
        return out

    def set_list_source(self, name: str, path: str) -> None:
        self.ensure_list(name)
        self.con.execute("UPDATE lists SET source = ? WHERE name = ?", (path, name))
        self.con.commit()

    def set_list_enabled(self, name: str, enabled: bool) -> None:
        self.con.execute("UPDATE lists SET enabled = ? WHERE name = ?", (int(bool(enabled)), name))
        self.con.commit()

    def introduced_today(self, now: float) -> int:
        return int(
            self.con.execute(
                "SELECT COUNT(*) FROM events WHERE result = 'intro' AND ts >= ?",
                (day_start(now),),
            ).fetchone()[0]
        )


def pick_word(store: Store, now: float) -> Word | None:
    due = store.due_words(now)
    if due:
        return due[0]
    if store.introduced_today(now) < NEW_PER_DAY:
        fresh = store.new_words(1)
        if fresh:
            return fresh[0]
    seen = [w for w in store.askable() if w.box >= 0]
    return min(seen, key=lambda w: (w.due_at, w.id)) if seen else None


def apply_srs(
    store: Store,
    word: Word,
    result: str,
    now: float,
    qtype: str = "",
    answer: str = "",
) -> None:
    if result == "intro":
        store.update_word(word.id, box=0, due_at=now + INTERVALS[0])
    elif result == "correct":
        next_box = min(max(word.box, 0) + 1, len(INTERVALS) - 1)
        store.update_word(word.id, box=next_box, due_at=now + INTERVALS[next_box])
    elif result == "wrong":
        store.update_word(word.id, box=0, due_at=now + RETRY)
    elif result == "skipped":
        store.update_word(word.id, due_at=now + RETRY)
    elif result == "hidden":
        store.set_hidden(word.id, True)
    store.log_event(word.id, qtype or ("intro" if result == "intro" else ""), result, answer, ts=now)


def _select_distractors(store: Store, word: Word, rng: random.Random) -> list[Word]:
    own_label = fold_ascii(choice_label(word.meaning))
    own_parts = {fold_ascii(p) for p in meaning_parts(word.meaning) if fold_ascii(p)}
    candidates = []
    for w in store.askable():
        if w.id == word.id:
            continue
        w_parts = {fold_ascii(p) for p in meaning_parts(w.meaning) if fold_ascii(p)}
        if own_parts & w_parts:
            continue
        candidates.append(w)

    rng.shuffle(candidates)
    # Önce aynı sözcük türü ve aynı liste tercih edilir; yetmezse diğer sözcük türlerinden tamamlanır
    candidates.sort(key=lambda w: (w.pos != word.pos, w.list_id != word.list_id))
    chosen: list[Word] = []
    seen_labels = {own_label}
    for w in candidates:
        lbl = fold_ascii(choice_label(w.meaning))
        if lbl and lbl not in seen_labels:
            chosen.append(w)
            seen_labels.add(lbl)
        if len(chosen) == 3:
            break
    return chosen


def build_question(store: Store, word: Word, lang: str, rng: random.Random) -> dict:
    is_tr = lang == "tr"
    if word.box == -1:
        body = highlight_word(word.example, word.word) if word.example else ""
        if word.translation:
            sep = "<br>" if body else ""
            body += f"{sep}<i>{html.escape(word.translation, quote=False)}</i>"
        q = {
            "wordId": word.id,
            "word": word.word,
            "meaning": word.meaning,
            "example": word.example,
            "translation": word.translation,
            "qtype": "intro",
            "title": f"{word.word} — {short_meaning(word.meaning)}",
            "prompt": "Yeni kelime" if is_tr else "New word",
            "bodyHtml": body,
            "choices": [],
            "correctIndex": -1,
        }
        store.set_db_setting("last_question_json", json.dumps(q, ensure_ascii=False))
        return q

    if word.box <= 1:
        pool = list(CHOICE_QTYPES)
    elif word.box < SETTLED_BOX:
        pool = list(QTYPES)
    else:
        pool = list(TYPED_QTYPES)

    if not word.example and "type_context" in pool:
        pool.remove("type_context")

    distractors = _select_distractors(store, word, rng)
    if len(distractors) < 3:
        pool = [qt for qt in pool if qt not in CHOICE_QTYPES]

    qtype = rng.choice(pool or ["type_word_meaning"])

    if qtype == "type_word_meaning":
        q = {
            "wordId": word.id,
            "word": word.word,
            "meaning": word.meaning,
            "example": word.example,
            "translation": word.translation,
            "qtype": qtype,
            "title": word.word,
            "prompt": "Anlamını yaz" if is_tr else "Type the meaning",
            "bodyHtml": "",
            "choices": [],
            "correctIndex": -1,
        }
    elif qtype == "type_context":
        q = {
            "wordId": word.id,
            "word": word.word,
            "meaning": word.meaning,
            "example": word.example,
            "translation": word.translation,
            "qtype": qtype,
            "title": f"Cümlede '{word.word}' ne demek?" if is_tr else f"What does '{word.word}' mean here?",
            "prompt": "Anlamını yaz" if is_tr else "Type the meaning",
            "bodyHtml": highlight_word(word.example, word.word),
            "choices": [],
            "correctIndex": -1,
        }
    else:
        options = [word] + distractors
        rng.shuffle(options)
        correct_idx = options.index(word)
        if qtype == "choice_meaning_word":
            q = {
                "wordId": word.id,
                "word": word.word,
                "meaning": word.meaning,
                "example": word.example,
                "translation": word.translation,
                "qtype": qtype,
                "title": choice_label(word.meaning),
                "prompt": "Doğru kelime hangisi?" if is_tr else "Which word matches?",
                "bodyHtml": "",
                "choices": [w.word for w in options],
                "correctIndex": correct_idx,
            }
        else:
            q = {
                "wordId": word.id,
                "word": word.word,
                "meaning": word.meaning,
                "example": word.example,
                "translation": word.translation,
                "qtype": qtype,
                "title": word.word,
                "prompt": "Doğru anlam hangisi?" if is_tr else "Choose the meaning",
                "bodyHtml": "",
                "choices": [choice_label(w.meaning) for w in options],
                "correctIndex": correct_idx,
            }

    store.set_db_setting("last_question_json", json.dumps(q, ensure_ascii=False))
    return q


def build_feedback(word: Word, qtype: str, correct: bool) -> dict:
    right_answer = word.word if qtype == "choice_meaning_word" else short_meaning(word.meaning)
    return {
        "correct": bool(correct),
        "rightAnswer": right_answer,
        "word": word.word,
        "meaning": short_meaning(word.meaning),
        "exampleHtml": highlight_word(word.example, word.word) if word.example else "",
    }


def _relative_day_label(ts: float, now: float, lang: str) -> str:
    days = int((day_start(now) - day_start(ts)) // DAY_SEC + 0.5)
    if lang == "tr":
        return "bugün" if days <= 0 else "dün" if days == 1 else f"{days} gün önce"
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days}d ago"


def word_to_dict(w: Word, last5: list[str] | None = None, history: list[str] | None = None) -> dict:
    d = {
        "id": w.id,
        "word": w.word,
        "meaning": w.meaning,
        "pos": w.pos,
        "example": w.example,
        "translation": w.translation,
        "listName": w.list_name,
        "hidden": bool(w.hidden),
        "enriched": bool(w.enriched),
        "box": w.box,
        "dueAt": w.due_at,
        "last5": last5 if last5 is not None else [],
    }
    if history is not None:
        d["history"] = history
        d["exampleHtml"] = highlight_word(w.example, w.word) if w.example else ""
    return d


def build_snapshot(store: Store, settings: dict, payload: dict | None = None) -> dict:
    p = payload or {}
    now = float(p.get("now") or time.time())
    lang = settings["language"]
    query = str(p.get("query") or "")
    list_filter = str(p.get("listFilter") or "")
    selected_id = int(p.get("selectedWordId") or 0)

    con = store.con
    answered_today = int(
        con.execute(
            "SELECT COUNT(*) FROM events WHERE result IN ('correct', 'wrong') AND ts >= ?",
            (day_start(now),),
        ).fetchone()[0]
    )
    recent_rows = con.execute(
        "SELECT w.id, w.word, COALESCE(w.created_at, ?), COALESCE(l.name, 'Custom')"
        " FROM words w LEFT JOIN lists l ON l.id = w.list_id"
        " WHERE w.hidden = 0 ORDER BY w.created_at DESC, w.id DESC LIMIT 4",
        (now,),
    ).fetchall()
    recent = [
        {
            "id": int(wid),
            "word": wtxt,
            "when": _relative_day_label(float(cts or now), now, lang),
            "how": ("kısayolla" if lang == "tr" else "captured")
            if lname in ("Custom", "Kendi")
            else lname,
        }
        for wid, wtxt, cts, lname in recent_rows
    ]

    since = day_start(now) - 29 * DAY_SEC
    right_30, total_30 = con.execute(
        "SELECT COALESCE(SUM(result = 'correct'), 0), COUNT(*)"
        " FROM events WHERE result IN ('correct', 'wrong') AND ts >= ?",
        (since,),
    ).fetchone()
    hardest_rows = con.execute(
        "SELECT w.id, w.word, COUNT(*) AS n"
        " FROM events e JOIN words w ON w.id = e.word_id"
        " WHERE e.result = 'wrong' AND e.ts >= ? AND w.hidden = 0"
        " GROUP BY e.word_id ORDER BY n DESC, w.word ASC LIMIT 9",
        (since,),
    ).fetchall()
    days = [0] * 30
    for (ts_val,) in con.execute(
        "SELECT ts FROM events WHERE result IN ('correct', 'wrong') AND ts >= ?",
        (since,),
    ):
        idx = max(0, min(29, int((day_start(float(ts_val)) - since) // DAY_SEC + 0.5)))
        days[idx] += 1

    type_buckets: dict[str, list[int]] = {}
    for qt, r_cnt, t_cnt in con.execute(
        "SELECT qtype, COALESCE(SUM(result = 'correct'), 0), COUNT(*)"
        " FROM events WHERE result IN ('correct', 'wrong') AND ts >= ? AND qtype != ''"
        " GROUP BY qtype",
        (since,),
    ):
        canon_qt = LEGACY_QTYPE_MAP.get(qt, qt)
        cur = type_buckets.setdefault(canon_qt, [0, 0])
        cur[0] += int(r_cnt)
        cur[1] += int(t_cnt)
    by_type = {
        qt: round(100 * vals[0] / vals[1]) for qt, vals in type_buckets.items() if vals[1] > 0
    }
    settled_count = int(
        con.execute(
            "SELECT COUNT(*) FROM words WHERE hidden = 0 AND box >= ?",
            (SETTLED_BOX,),
        ).fetchone()[0]
    )
    total_words = int(
        con.execute("SELECT COUNT(*) FROM words WHERE hidden = 0").fetchone()[0]
    )

    words_list = store.query_words(query=query, list_filter=list_filter)
    l5 = store.last5_map([w.id for w in words_list])
    words_out = [word_to_dict(w, last5=l5.get(w.id, [])) for w in words_list]

    selected_word = None
    if selected_id > 0:
        sw = store.get(selected_id)
        if sw:
            hist = store.full_history(sw.id, answered_only=True)
            selected_word = word_to_dict(sw, last5=hist[-5:], history=hist)
    elif words_list:
        sw = words_list[0]
        hist = store.full_history(sw.id, answered_only=True)
        selected_word = word_to_dict(sw, last5=hist[-5:], history=hist)

    return {
        "ok": True,
        "dbPath": str(store.path),
        "settings": settings,
        "hasCustomApiKey": has_custom_api_key(),
        "today": {
            "answered": answered_today,
            "goal": settings["dailyGoal"],
            "nextInMin": settings["intervalMin"],
            "mutedUntil": settings["mutedUntil"],
            "recent": recent,
            "totalWords": total_words,
        },
        "stats": {
            "answeredToday": days[-1],
            "accuracy": round(100 * int(right_30) / int(total_30)) if int(total_30) else 0,
            "settled": settled_count,
            "totalWords": total_words,
            "hardest": [{"id": int(wid), "word": w, "misses": int(n)} for wid, w, n in hardest_rows],
            "days": days,
            "byType": by_type,
        },
        "lists": store.lists_summary(),
        "words": words_out,
        "selectedWord": selected_word,
        "legacyAvailable": legacy_db_path().is_file(),
        "providers": provider_statuses(),
    }


def handle_command(cmd: str, payload: dict) -> dict:
    settings = load_settings()
    store = Store(db_path())
    try:
        if cmd == "snapshot":
            return build_snapshot(store, settings, payload)

        if cmd == "save-settings":
            updated = save_settings_file(payload)
            return build_snapshot(store, updated, payload)

        if cmd == "add-word":
            raw_word = str(payload.get("word") or "").strip()
            if not raw_word:
                return {"ok": False, "error": "Word is required"}
            meaning = str(payload.get("meaning") or "").strip()
            pos = str(payload.get("pos") or "").strip()
            example = str(payload.get("example") or "").strip()
            translation = str(payload.get("translation") or "").strip()
            list_name = str(payload.get("listName") or "Custom").strip() or "Custom"
            enriched = bool(meaning)
            wid = store.add_word(
                raw_word,
                meaning=meaning,
                pos=pos,
                example=example,
                translation=translation,
                list_name=list_name,
                enriched=enriched,
            )
            if wid is None:
                existing = store.get_by_text(raw_word)
                snap = build_snapshot(
                    store,
                    settings,
                    {**payload, "selectedWordId": existing.id if existing else 0},
                )
                snap["duplicate"] = True
                snap["wordId"] = existing.id if existing else 0
                snap["needsEnrich"] = bool(existing and not existing.enriched)
                return snap
            snap = build_snapshot(store, settings, {**payload, "selectedWordId": wid})
            snap["duplicate"] = False
            snap["wordId"] = wid
            snap["needsEnrich"] = not enriched
            return snap

        if cmd == "update-word":
            wid = int(payload.get("wordId") or 0)
            cur = store.get(wid)
            if not cur:
                return {"ok": False, "error": "Word not found"}
            updates = {}
            if "word" in payload:
                w_clean = " ".join(str(payload["word"] or "").strip().lower().split())
                if w_clean:
                    updates["word"] = w_clean
            if "meaning" in payload:
                m_clean = str(payload["meaning"] or "").strip()
                updates["meaning"] = m_clean
                updates["enriched"] = int(bool(m_clean))
                if m_clean and "pos" not in payload:
                    updates["pos"] = guess_pos(m_clean)
            if "pos" in payload and str(payload["pos"] or "").strip():
                updates["pos"] = str(payload["pos"]).strip()
            if "example" in payload:
                updates["example"] = str(payload["example"] or "").strip()
            if "translation" in payload:
                updates["translation"] = str(payload["translation"] or "").strip()
            if "listName" in payload and str(payload["listName"] or "").strip():
                updates["list_id"] = store.ensure_list(str(payload["listName"]).strip())
            store.update_word(wid, **updates)
            return build_snapshot(store, settings, {**payload, "selectedWordId": wid})

        if cmd == "set-hidden":
            wid = int(payload.get("wordId") or 0)
            hidden = bool(payload.get("hidden", True))
            if not store.get(wid):
                return {"ok": False, "error": "Word not found"}
            store.set_hidden(wid, hidden)
            return build_snapshot(store, settings, payload)

        if cmd == "set-list-enabled":
            name = str(payload.get("name") or "").strip()
            enabled = bool(payload.get("enabled", True))
            store.set_list_enabled(name, enabled)
            return build_snapshot(store, settings, payload)

        if cmd == "list-words":
            name = str(payload.get("name") or "").strip()
            rows = store.query_words(list_filter=name)
            return {
                "ok": True,
                "name": name,
                "words": [
                    {
                        "id": w.id,
                        "word": w.word,
                        "meaning": w.meaning,
                        "example": w.example,
                        "translation": w.translation,
                        "box": w.box,
                    }
                    for w in rows
                ],
            }

        if cmd == "next-question":
            now = float(payload.get("now") or time.time())
            rep = payload.get("replaceQuestion")
            if isinstance(rep, dict) and rep.get("wordId"):
                prev_word = store.get(int(rep["wordId"]))
                if prev_word:
                    prev_qt = str(rep.get("qtype") or "")
                    apply_srs(
                        store,
                        prev_word,
                        "intro" if prev_qt == "intro" else "skipped",
                        now,
                        qtype=prev_qt,
                    )
            req_wid = int(payload.get("wordId") or 0)
            target = store.get(req_wid) if req_wid > 0 else pick_word(store, now)
            if not target or not target.meaning:
                return {"ok": True, "question": None}
            seed_val = payload.get("seed")
            rng = random.Random(seed_val) if seed_val is not None else random.Random()
            q = build_question(store, target, settings["language"], rng)
            return {"ok": True, "question": q}

        if cmd == "grade-question":
            now = float(payload.get("now") or time.time())
            wid = int(payload.get("wordId") or 0)
            qtype = str(payload.get("qtype") or "")
            action = str(payload.get("action") or "")
            word = store.get(wid)
            if not word:
                return {"ok": False, "error": "Word not found"}

            if action == "intro":
                apply_srs(store, word, "intro", now, qtype="intro")
                snap = build_snapshot(store, settings, payload)
                snap.update({"status": "recorded", "result": "intro", "feedback": None})
                return snap

            if action == "skip":
                res_kind = "intro" if qtype == "intro" else "skipped"
                apply_srs(store, word, res_kind, now, qtype=qtype)
                snap = build_snapshot(store, settings, payload)
                snap.update({"status": "recorded", "result": res_kind, "feedback": None})
                return snap

            if action == "hide":
                apply_srs(store, word, "hidden", now, qtype=qtype)
                snap = build_snapshot(store, settings, payload)
                snap.update({"status": "recorded", "result": "hidden", "feedback": None})
                return snap

            if action == "choice":
                choice_idx = int(payload.get("choiceIndex", -1))
                correct_idx = payload.get("correctIndex")
                answer_label = str(payload.get("choiceText") or "")
                if correct_idx is None:
                    raw_last = store.db_setting("last_question_json", "")
                    if raw_last:
                        try:
                            lq = json.loads(raw_last)
                            if int(lq.get("wordId") or 0) == wid and lq.get("qtype") == qtype:
                                correct_idx = int(lq.get("correctIndex", -2))
                                choices = lq.get("choices") or []
                                if 0 <= choice_idx < len(choices) and not answer_label:
                                    answer_label = str(choices[choice_idx])
                        except ValueError:
                            correct_idx = -2
                is_ok = choice_idx >= 0 and correct_idx is not None and choice_idx == int(correct_idx)
                res_kind = "correct" if is_ok else "wrong"
                apply_srs(store, word, res_kind, now, qtype=qtype, answer=answer_label)
                snap = build_snapshot(store, settings, payload)
                snap.update(
                    {
                        "status": "recorded",
                        "result": res_kind,
                        "feedback": build_feedback(word, qtype, is_ok),
                    }
                )
                return snap

            if action == "typed":
                typed = str(payload.get("typedText") or "").strip()
                if not typed:
                    apply_srs(store, word, "skipped", now, qtype=qtype)
                    snap = build_snapshot(store, settings, payload)
                    snap.update({"status": "recorded", "result": "skipped", "feedback": None})
                    return snap
                if match_answer(typed, word.meaning):
                    apply_srs(store, word, "correct", now, qtype=qtype, answer=typed)
                    snap = build_snapshot(store, settings, payload)
                    snap.update(
                        {
                            "status": "recorded",
                            "result": "correct",
                            "feedback": build_feedback(word, qtype, True),
                        }
                    )
                    return snap
                if ai_can_run(settings):
                    return {
                        "ok": True,
                        "status": "needs_ai_judge",
                        "wordId": word.id,
                        "qtype": qtype,
                        "typedText": typed,
                    }
                apply_srs(store, word, "wrong", now, qtype=qtype, answer=typed)
                snap = build_snapshot(store, settings, payload)
                snap.update(
                    {
                        "status": "recorded",
                        "result": "wrong",
                        "feedback": build_feedback(word, qtype, False),
                    }
                )
                return snap

            return {"ok": False, "error": f"Unknown grade action: {action}"}

        return {"ok": False, "error": f"Unknown command: {cmd}"}
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(json.dumps({"ok": False, "error": "Missing command"}))
        return 1
    cmd = args[0]
    raw_arg = args[1] if len(args) > 1 else "{}"
    try:
        if raw_arg == "-":
            stdin_txt = sys.stdin.read().strip()
            payload = json.loads(stdin_txt) if stdin_txt else {}
        else:
            payload = json.loads(raw_arg) if raw_arg.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON payload: {exc}"}))
        return 1

    try:
        result = handle_command(cmd, payload)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
