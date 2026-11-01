import csv
from dataclasses import dataclass
import html
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

# Aralıklı tekrar sabitleri (eski kelime uygulamasıyla birebir aynı)
INTERVALS = [600, 1800, 7200, 86400, 3 * 86400, 7 * 86400]
RETRY = 600
SKIP_DELAY = 1800  # ✕ ile atlanan kelime "şimdi değil" demektir: yanlış cevaptan daha geç döner
RECENT_GAP = 3  # son bu kadar soruda gelen kelime, başka seçenek varken yeniden sorulmaz
REVIEWS_PER_NEW = 2  # bu kadar tekrar sorusundan sonra sırada yeni kelime varsa o tanıtılır
SETTLED_BOX = 4
NEW_PER_DAY = 20
DAY_SEC = 86400
AI_TIMEOUT = 45
HTTP_TIMEOUT = 5.0

QTYPES = ("type_word_meaning", "type_context", "choice_meaning_word", "choice_word_meaning")
CHOICE_QTYPES = ("choice_meaning_word", "choice_word_meaning")
TYPED_QTYPES = ("type_word_meaning", "type_context")

LEGACY_QTYPE_MAP = {
    "type_en_tr": "type_word_meaning",
    "type_context": "type_context",
    "choice_tr_en": "choice_meaning_word",
    "choice_en_tr": "choice_word_meaning",
}

HEADER_WORDS = {
    "kelime",
    "kelimeler",
    "word",
    "words",
    "anlam",
    "anlamı",
    "meaning",
    "fiil",
    "eylem",
    "örnek",
    "örnek cümle",
    "example",
    "çeviri",
    "türkçe çevirisi",
    "translation",
    "no",
    "sıra",
}
DEFAULT_COLUMNS = (0, 1, 2, 3)

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
# hidden sütunu kelimenin durumunu taşır: 0 sorulur, 1 gizli ("bir daha gösterme"), 2 öğrendim
LEARNED = 2
ASKABLE_WHERE = "w.hidden = 0 AND w.meaning != '' AND COALESCE(l.enabled, 1) = 1"

DEFAULT_SETTINGS = {
    "language": "en",
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

# ISO-639-1 ve ISO-639-3 dil kodu eşlemesi (serbest kullanıcı girişinden çözülür)
LANG_CODES: dict[str, tuple[str, str]] = {
    "english": ("en", "eng"),
    "ingilizce": ("en", "eng"),
    "en": ("en", "eng"),
    "eng": ("en", "eng"),
    "turkish": ("tr", "tur"),
    "türkçe": ("tr", "tur"),
    "turkce": ("tr", "tur"),
    "tr": ("tr", "tur"),
    "tur": ("tr", "tur"),
    "german": ("de", "deu"),
    "deutsch": ("de", "deu"),
    "almanca": ("de", "deu"),
    "de": ("de", "deu"),
    "deu": ("de", "deu"),
    "spanish": ("es", "spa"),
    "español": ("es", "spa"),
    "espanol": ("es", "spa"),
    "ispanyolca": ("es", "spa"),
    "es": ("es", "spa"),
    "spa": ("es", "spa"),
    "french": ("fr", "fra"),
    "français": ("fr", "fra"),
    "francais": ("fr", "fra"),
    "fransızca": ("fr", "fra"),
    "fr": ("fr", "fra"),
    "fra": ("fr", "fra"),
    "italian": ("it", "ita"),
    "italiano": ("it", "ita"),
    "italyanca": ("it", "ita"),
    "it": ("it", "ita"),
    "ita": ("it", "ita"),
    "portuguese": ("pt", "por"),
    "português": ("pt", "por"),
    "portekizce": ("pt", "por"),
    "pt": ("pt", "por"),
    "por": ("pt", "por"),
    "russian": ("ru", "rus"),
    "русский": ("ru", "rus"),
    "rusça": ("ru", "rus"),
    "ru": ("ru", "rus"),
    "rus": ("ru", "rus"),
    "japanese": ("ja", "jpn"),
    "日本語": ("ja", "jpn"),
    "japonca": ("ja", "jpn"),
    "ja": ("ja", "jpn"),
    "jpn": ("ja", "jpn"),
    "korean": ("ko", "kor"),
    "한국어": ("ko", "kor"),
    "korece": ("ko", "kor"),
    "ko": ("ko", "kor"),
    "kor": ("ko", "kor"),
    "arabic": ("ar", "ara"),
    "العربية": ("ar", "ara"),
    "arapça": ("ar", "ara"),
    "ar": ("ar", "ara"),
    "ara": ("ar", "ara"),
    "dutch": ("nl", "nld"),
    "nederlands": ("nl", "nld"),
    "felemenkçe": ("nl", "nld"),
    "nl": ("nl", "nld"),
    "nld": ("nl", "nld"),
    "polish": ("pl", "pol"),
    "polski": ("pl", "pol"),
    "lehçe": ("pl", "pol"),
    "pl": ("pl", "pol"),
    "pol": ("pl", "pol"),
    "swedish": ("sv", "swe"),
    "svenska": ("sv", "swe"),
    "isveççe": ("sv", "swe"),
    "sv": ("sv", "swe"),
    "swe": ("sv", "swe"),
    "chinese": ("zh", "cmn"),
    "中文": ("zh", "cmn"),
    "çince": ("zh", "cmn"),
    "zh": ("zh", "cmn"),
    "cmn": ("zh", "cmn"),
    "greek": ("el", "ell"),
    "ελληνικά": ("el", "ell"),
    "yunanca": ("el", "ell"),
    "el": ("el", "ell"),
    "ell": ("el", "ell"),
}

ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "meaning": {"type": "string"},
        "pos": {"type": "string", "enum": ["verb", "noun", "adjective", "adverb", "other"]},
        "example": {"type": "string"},
        "translation": {"type": "string"},
    },
    "required": ["meaning", "pos", "example", "translation"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"accept": {"type": "boolean"}},
    "required": ["accept"],
}

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "translation": {"type": "string"},
        "source": {"type": "string", "enum": ["target", "meaning"]},
    },
    "required": ["translation", "source"],
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


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def starter_csv_path() -> Path:
    return repo_root() / "data" / "starter-en.csv"


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


def read_custom_api_key() -> str:
    p = api_key_path()
    try:
        return p.read_text(encoding="utf-8").strip() if p.is_file() else ""
    except OSError:
        return ""


def write_custom_api_key(key: str) -> None:
    clean = (key or "").strip()
    p = api_key_path()
    if not clean:
        clear_custom_api_key()
        return
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (clean + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def clear_custom_api_key() -> None:
    p = api_key_path()
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def has_custom_api_key() -> bool:
    return bool(read_custom_api_key())


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
        return bool(
            str(settings.get("customBaseUrl") or "").strip()
            and str(settings.get("customModel") or "").strip()
        )
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
        if len(a) >= 5 and len(p) >= 6:
            max_dist = 2 if len(p) >= 10 else 1
            dist = _levenshtein(a, p)
            if dist <= max_dist and not (dist == 1 and len(p) <= 7 and a[0] != p[0]):
                return True
    return False


def guess_pos(meaning: str) -> str:
    first = (meaning or "").split(",")[0].strip().lower()
    if first.endswith(("mak", "mek")) or first.startswith("to "):
        return "verb"
    return "other"


def normalize_pos(raw_pos: str, meaning: str = "") -> str:
    p = (raw_pos or "").strip().lower()
    if p in ("verb", "noun", "adjective", "adverb", "other"):
        return p
    if "verb" in p:
        return "verb"
    if "noun" in p:
        return "noun"
    if "adj" in p:
        return "adjective"
    if "adv" in p:
        return "adverb"
    return guess_pos(meaning) if meaning else "other"


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


# --- CSV & PDF İçe Aktarma ---


@dataclass
class ImportRow:
    word: str
    meaning: str
    example: str = ""
    translation: str = ""
    pos: str = ""

    def to_dict(self) -> dict:
        return {
            "word": self.word,
            "meaning": self.meaning,
            "example": self.example,
            "translation": self.translation,
            "pos": self.pos,
        }


def _clean_cell(val) -> str:
    return " ".join(str(val or "").split())


def _is_header_cells(cells: list[str]) -> bool:
    lowered = {tr_lower(_clean_cell(c)) for c in cells if _clean_cell(c)}
    return len(lowered & HEADER_WORDS) >= 2


def _normalize_columns(cols) -> tuple[int, int, int, int]:
    if isinstance(cols, list | tuple) and len(cols) >= 2:
        padded = [int(cols[i]) if i < len(cols) else i for i in range(4)]
        return (padded[0], padded[1], padded[2], padded[3])
    return DEFAULT_COLUMNS


def read_csv_raw(path: Path | str, limit: int = 10) -> list[list[str]]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [
        [_clean_cell(c) for c in r]
        for r in csv.reader(io.StringIO(text), dialect)
        if any(str(c).strip() for c in r)
    ]
    return rows[:limit]


def read_csv_rows(path: Path | str, columns=DEFAULT_COLUMNS) -> list[ImportRow]:
    cols = _normalize_columns(columns)
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    lines = [
        r for r in csv.reader(io.StringIO(text), dialect) if any(str(c).strip() for c in r)
    ]
    if lines and _is_header_cells(lines[0]):
        lines = lines[1:]
    out: list[ImportRow] = []
    for r in lines:
        vals = [
            _clean_cell(r[idx]) if 0 <= idx < len(r) else ""
            for idx in cols
        ]
        if vals[0] and vals[1]:
            out.append(ImportRow(vals[0], vals[1], vals[2], vals[3]))
    return out


_LINE_SEG_RE = re.compile(r"\S+(?:\s\S+)*")
_ROW_HEAD_RE = re.compile(r"^(\s*)(\d{1,4})(\s{2,})(.+)$")
_PAGE_FOOTER_RE = re.compile(r"(?i)^(sayfa|page)\s*\d+(\s*/\s*\d+)?$")


def parse_pdftotext_layout(text: str) -> list[ImportRow]:
    """pdftotext -layout çıktısından 5 sütunlu (sıra, kelime, anlam, örnek, çeviri) satırları çözer."""
    rows: list[ImportRow] = []
    for page in (text or "").split("\f"):
        current_cols: list[list[str]] | None = None
        col_x: list[int] = []

        def flush_current() -> None:
            nonlocal current_cols
            if current_cols is not None:
                merged = [_clean_cell(" ".join(parts)) for parts in current_cols]
                if merged[0] and merged[1]:
                    rows.append(ImportRow(merged[0], merged[1], merged[2], merged[3]))
                current_cols = None

        for raw_line in page.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if _PAGE_FOOTER_RE.match(stripped):
                continue

            m_head = _ROW_HEAD_RE.match(line)
            if m_head:
                rest_start = m_head.start(4)
                segs = [
                    (rest_start + m.start(), m.group(0))
                    for m in _LINE_SEG_RE.finditer(m_head.group(4))
                ]
                if len(segs) >= 2:
                    flush_current()
                    current_cols = [[], [], [], []]
                    col_x = []
                    for idx, (sx, stxt) in enumerate(segs[:4]):
                        current_cols[idx].append(stxt)
                        col_x.append(sx)
                    if len(segs) > 4:
                        current_cols[3].extend(stxt for _, stxt in segs[4:])
                    continue

            # Devam satırı mı yoksa başlık satırı mı?
            segs_all = [(m.start(), m.group(0)) for m in _LINE_SEG_RE.finditer(line)]
            if _is_header_cells([s for _, s in segs_all]):
                flush_current()
                continue
            if current_cols is None or not col_x:
                continue

            # Devam satırındaki parçaları en yakın sütun X-ofsetine ekle
            for sx, stxt in segs_all:
                nearest_idx = min(range(len(col_x)), key=lambda i: abs(sx - col_x[i]))
                current_cols[nearest_idx].append(stxt)

        flush_current()
    return rows


def read_pdf_rows(path: Path | str) -> list[ImportRow]:
    p_str = str(path)
    pdftotext_bin = find_bin("pdftotext") or "pdftotext"
    try:
        proc = subprocess.run(
            [pdftotext_bin, "-layout", p_str, "-"],
            capture_output=True,
            text=True,
            timeout=25,
            env=child_env(),
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parsed = parse_pdftotext_layout(proc.stdout)
            if parsed:
                return parsed
    except (OSError, subprocess.SubprocessError):
        pass

    # Sistemde isteğe bağlı pdfplumber varsa yedek olarak dene
    try:
        import pdfplumber  # type: ignore[import-not-found]

        out: list[ImportRow] = []
        with pdfplumber.open(p_str) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for r in table:
                        if len(r) >= 5 and _clean_cell(r[0]).isdigit():
                            cells = [_clean_cell(c) for c in r[1:5]]
                            if cells[0] and cells[1]:
                                out.append(ImportRow(*cells))
        return out
    except Exception:  # noqa: BLE001
        return []


TEXT_SUFFIXES = (".pdf", ".docx", ".odt", ".txt", ".md")
_POS_ABBR = {
    "n": "noun", "noun": "noun", "v": "verb", "verb": "verb", "pv": "verb", "phr": "verb",
    "adj": "adjective", "a": "adjective", "adv": "adverb", "prep": "other", "conj": "other",
    "pron": "other", "exp": "other", "phrase": "other", "idiom": "other",
}
_LIST_MARK_RE = re.compile(r"^\s*(?:\d{1,4}\s*[.)\-]\s*|\d{1,4}\s{2,}|[-•*·▪●–]\s+)")
_POS_LINE_RE = re.compile(r"^(?P<w>[^()\t|:=]+?)\s*\((?P<pos>[A-Za-z. ]{1,8})\)\s*[:=\-–—]?\s*(?P<m>.+)$")
_POS_SUFFIX_RE = re.compile(r"^(?P<w>.+?)\s*\((?P<pos>[A-Za-z. ]{1,8})\)$")
_MD_MARK_RE = re.compile(r"^#{1,6}\s+|\*\*|__|`")
_INDEX_CELL_RE = re.compile(r"^\d{1,4}[.)]?$")
# Sıra önemli: çok sütunlu ayırıcılar önce, tek seferlik "kelime ayırıcı anlam" ayırıcıları sonra;
# " - " ":"dan önce gelir ki "run - koşmak (örn: hızlı)" anlamın içinden bölünmesin.
_MULTI_SPLIT_RE = (re.compile(r"\t+"), re.compile(r"\s*\|\s*"), re.compile(r"\s{2,}"))
_PAIR_SPLIT_RE = (
    re.compile(r"\s*=\s*"), re.compile(r"\s+[–—-]\s+"), re.compile(r"\s*:\s+|\s*:(?=\S)"),
    re.compile(r"\s*;\s*"),
)


def _office_lines(el, tag_of, row_tag: str, cell_tag: str, para_tags: tuple[str, ...], para_text) -> list[str]:
    """Belge ağacını sırayla gezer: tablo satırı hücreleri sekmeyle birleşir, paragraf kendi satırı olur."""
    out: list[str] = []
    for child in el:
        tag = tag_of(child)
        if tag == row_tag:
            cells = [
                _clean_cell(" ".join(para_text(par) for par in c.iter() if tag_of(par) in para_tags))
                for c in child if tag_of(c) == cell_tag
            ]
            out.append("\t".join(cells))
        elif tag in para_tags:
            out.append(para_text(child))
        else:
            out.extend(_office_lines(child, tag_of, row_tag, cell_tag, para_tags, para_text))
    return out


def _docx_text(path: Path) -> str:
    """DOCX/ODT paragraflarını ve tablo satırlarını (hücreler sekmeyle) düz metne çevirir."""
    tag_of = lambda e: e.tag.rsplit("}", 1)[-1]  # noqa: E731
    with zipfile.ZipFile(path) as zf:
        odt = path.suffix.lower() == ".odt"
        root = ET.fromstring(zf.read("content.xml" if odt else "word/document.xml"))
    if odt:
        def odt_para(par) -> str:
            parts = [par.text or ""]
            for el in par:
                t = tag_of(el)
                parts.append("\t" if t == "tab" else "\n" if t == "line-break" else "".join(el.itertext()))
                parts.append(el.tail or "")
            return "".join(parts)
        return "\n".join(_office_lines(root, tag_of, "table-row", "table-cell", ("p", "h"), odt_para))

    def docx_para(par) -> str:
        parts = []
        for el in par.iter():
            t = tag_of(el)
            if t == "t":
                parts.append(el.text or "")
            elif t == "tab":
                parts.append("\t")
            elif t in ("br", "cr"):
                parts.append("\n")
        return "".join(parts)

    return "\n".join(_office_lines(root, tag_of, "tr", "tc", ("p",), docx_para))


def extract_text(path: Path | str) -> str:
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".pdf":
        try:
            proc = subprocess.run(
                [find_bin("pdftotext") or "pdftotext", "-layout", str(p), "-"],
                capture_output=True, text=True, timeout=25, env=child_env(), check=False,
            )
            return proc.stdout if proc.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    if suf in (".docx", ".odt"):
        try:
            return _docx_text(p)
        except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
            return ""
    return p.read_text(encoding="utf-8-sig", errors="replace")


def _valid_pair(word: str, meaning: str) -> bool:
    has_alpha = lambda t: any(ch.isalpha() for ch in t)  # noqa: E731
    return (
        bool(word) and bool(meaning) and has_alpha(word) and has_alpha(meaning)
        and len(word) <= 48 and len(word.split()) <= 5
        # Rakam ya da ayırıcı taşıyan "kelime" başlık/bölme hatasıdır: "Unit 1", "fall - sonbahar".
        and not any(ch.isdigit() for ch in word)
        and not any(sep in word for sep in (":", "=", "|", "\t", " - ", " – ", " — "))
    )


def _known_pos(raw: str) -> str | None:
    return _POS_ABBR.get(raw.strip(" .").lower())


def _split_pos(word: str) -> tuple[str, str]:
    """'constant (adj)' → ('constant', 'adjective'); tanınmayan parantez kelimede kalır."""
    m = _POS_SUFFIX_RE.match(word)
    if m and _known_pos(m.group("pos")) is not None:
        return _clean_cell(m.group("w")), _known_pos(m.group("pos")) or ""
    return word, ""


def parse_vocab_line(line: str) -> ImportRow | None:
    """Tek satırı (kelime, anlam[, örnek, çeviri]) olarak çözer; tanınmazsa None."""
    text = _MD_MARK_RE.sub("", line.rstrip()).strip()
    text = _LIST_MARK_RE.sub("", text, count=1).strip()
    if not text:
        return None
    for rx in _MULTI_SPLIT_RE:
        cells = [_clean_cell(c) for c in rx.split(text) if _clean_cell(c)]
        if len(cells) >= 3 and _INDEX_CELL_RE.match(cells[0]):
            cells = cells[1:]
        if len(cells) >= 2:
            if _is_header_cells(cells):
                return None
            cells += [""] * (4 - len(cells))
            word, pos = _split_pos(cells[0])
            if _valid_pair(word, cells[1]):
                return ImportRow(word, cells[1], cells[2], " ".join(cells[3:]).strip(), pos=pos)
    m = _POS_LINE_RE.match(text)
    if m and _known_pos(m.group("pos")) is not None:
        word, meaning = _clean_cell(m.group("w")), _clean_cell(m.group("m"))
        if _valid_pair(word, meaning):
            return ImportRow(word, meaning, pos=_known_pos(m.group("pos")) or "")
    for rx in _PAIR_SPLIT_RE:
        parts = rx.split(text, maxsplit=1)
        if len(parts) == 2:
            word, meaning = _clean_cell(parts[0]), _clean_cell(parts[1])
            if _is_header_cells([word, meaning]):
                return None
            word, pos = _split_pos(word)
            if _valid_pair(word, meaning):
                return ImportRow(word, meaning, pos=pos)
    return None


def parse_vocab_text(text: str) -> tuple[list[ImportRow], list[str]]:
    """Serbest biçimli liste metnini satır satır çözer; (satırlar, tanınmayan satırlar) döner."""
    rows: list[ImportRow] = []
    unparsed: list[str] = []
    for raw in (text or "").replace("\f", "\n").splitlines():
        stripped = _clean_cell(raw)
        if not stripped or _PAGE_FOOTER_RE.match(stripped) or not any(ch.isalpha() for ch in stripped):
            continue
        row = parse_vocab_line(raw)
        if row:
            rows.append(row)
        elif not _is_header_cells(stripped.split()):
            unparsed.append(stripped)
    return rows, unparsed


def word_key(word: str) -> str:
    """Store.add_word ile aynı anahtar (UNIQUE sütunu): küçük harf + tek boşluk."""
    return " ".join((word or "").strip().lower().split())


def dedupe_rows(rows: list[ImportRow]) -> list[ImportRow]:
    seen: set[str] = set()
    out = []
    for r in rows:
        key = word_key(r.word)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


AI_IMPORT_MAX_LINES = 120
AI_IMPORT_CHUNK = 30
IMPORT_ROWS_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "meaning": {"type": "string"},
                    "example": {"type": "string"},
                    "translation": {"type": "string"},
                },
                "required": ["word", "meaning", "example", "translation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
}


def ai_parse_lines(
    lines: list[str], settings: dict, runner=subprocess.run
) -> tuple[list[ImportRow], int]:
    """Tanınmayan satırların ilk AI_IMPORT_MAX_LINES kadarını AI ile çözer.

    (satırlar, okunan satır sayısı) döner; ilk başarısız parçada durur ki kalan satırlar yeniden denenebilsin.
    """
    out: list[ImportRow] = []
    consumed = 0
    todo = lines[:AI_IMPORT_MAX_LINES]
    for i in range(0, len(todo), AI_IMPORT_CHUNK):
        chunk = todo[i : i + AI_IMPORT_CHUNK]
        prompt = (
            f"These lines come from a vocabulary list document ({settings['targetLang']} words, "
            f"{settings['meaningLang']} meanings). Extract every vocabulary entry as word + meaning, "
            "plus example sentence and its translation only if present in the text (else empty string). "
            "Skip titles, headings and other non-vocabulary lines. Do not invent entries.\n\n"
            + "\n".join(chunk)
        )
        res = call_ai_structured(prompt, IMPORT_ROWS_SCHEMA, settings, runner=runner, max_tokens=3000)
        if not isinstance(res, dict) or not isinstance(res.get("rows"), list):
            break
        consumed += len(chunk)
        for item in res["rows"]:
            if not isinstance(item, dict):
                continue
            vals = [_clean_cell(item.get(k)) for k in ("word", "meaning", "example", "translation")]
            if _valid_pair(vals[0], vals[1]):
                out.append(ImportRow(*vals))
    return out, consumed


def read_text_import(path: Path | str) -> tuple[list[ImportRow], list[str]]:
    p = Path(path)
    text = extract_text(p)
    rows, unparsed = parse_vocab_text(text)
    if p.suffix.lower() == ".pdf":
        # Numaralı tablo bulunduysa sütun konumuna bakan çözücü kazanır: hücre devam satırlarını birleştirir.
        table_rows = parse_pdftotext_layout(text) or (read_pdf_rows(p) if not rows else [])
        valid = [r for r in table_rows if _valid_pair(r.word, r.meaning)]
        # İçindekiler gibi tek bir numaralı satır her şeyi tek hücreye yapıştırabilir: geçersizse satır çözücü kalır.
        if valid and len(valid) * 2 >= len(table_rows):
            return dedupe_rows(valid), []
    return dedupe_rows(rows), unparsed


def read_import_rows(path: Path | str, columns=DEFAULT_COLUMNS) -> list[ImportRow]:
    p = Path(path)
    if p.suffix.lower() in TEXT_SUFFIXES:
        return read_text_import(p)[0]
    return read_csv_rows(p, columns=columns)


def rows_from_payload(items) -> list[ImportRow]:
    out = []
    for item in (items or [])[:5000]:
        if not isinstance(item, dict):
            continue
        vals = [_clean_cell(item.get(k)) for k in ("word", "meaning", "example", "translation")]
        if _valid_pair(vals[0], vals[1]):
            out.append(ImportRow(*vals, pos=_clean_cell(item.get("pos"))))
    return out


def default_list_name_for(path: Path) -> str:
    stem = path.stem.strip()
    head, _, num = stem.rpartition("-")
    if head.lower() in ("kelimeler", "eylemler", "deck", "unit") and num.isdigit():
        return f"{head.capitalize()}-{num}"
    return stem or "Imported"


def import_file_into_store(
    store: "Store",
    path: Path | str,
    list_name: str | None = None,
    columns=DEFAULT_COLUMNS,
    rows: list[ImportRow] | None = None,
) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"File not found: {p}"}
    if rows is None:
        rows = read_import_rows(p, columns=columns)
    name = (list_name or "").strip() or default_list_name_for(p)
    store.set_list_source(name, str(p.resolve()))
    added = 0
    enrich_ids: list[int] = []
    for r in rows:
        wid = store.add_word(
            r.word,
            meaning=r.meaning,
            pos=normalize_pos(r.pos, r.meaning),
            example=r.example,
            translation=r.translation,
            list_name=name,
            # Örneksiz kelimede enriched=False: açılınca sözlük/AI yalnız boş örneği doldurur, anlamı ezmez.
            enriched=bool(r.example),
        )
        if wid is not None:
            added += 1
            if not r.example:
                enrich_ids.append(wid)
    return {
        "ok": True,
        "listName": name,
        # Örneksiz eklenen kelimeler: istemci bunları boşta kalan arka plan kuyruğunda tek tek zenginleştirir.
        "enrichIds": enrich_ids,
        "added": added,
        "skipped": len(rows) - added,
        "total": len(rows),
    }


# --- Hibrit Ücretsiz Sözlük + İsteğe Bağlı AI ---


def resolve_lang_codes(lang_name: str, fallback: tuple[str, str]) -> tuple[str, str]:
    key = tr_lower((lang_name or "").strip())
    if not key:
        return fallback
    if key in LANG_CODES:
        return LANG_CODES[key]
    first_word = key.split()[0].strip("()[]{}")
    if first_word in LANG_CODES:
        return LANG_CODES[first_word]
    if len(first_word) == 2 and first_word.isalpha():
        return (first_word, first_word)
    if len(first_word) == 3 and first_word.isalpha():
        return (first_word[:2], first_word)
    return fallback


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout: float = HTTP_TIMEOUT):
    req_headers = {"User-Agent": "Lexis-Omarchy/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _http_post_json(
    url: str,
    body: dict,
    headers: dict[str, str] | None = None,
    timeout: float = float(AI_TIMEOUT),
):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req_headers = {
        "User-Agent": "Lexis-Omarchy/1.0",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=raw, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _wiktionary_base() -> str:
    return (
        os.environ.get("LEXIS_WIKTIONARY_URL")
        or "https://freedictionaryapi.com/api/v1/entries"
    ).rstrip("/")


def _tatoeba_url() -> str:
    return (
        os.environ.get("LEXIS_TATOEBA_URL")
        or "https://tatoeba.org/en/api_v0/search"
    ).rstrip("/")


def _mymemory_url() -> str:
    return (
        os.environ.get("LEXIS_MYMEMORY_URL")
        or "https://api.mymemory.translated.net/get"
    ).rstrip("/")


def _mymemory_translate(text: str, src_iso2: str, dst_iso2: str) -> str:
    clean = (text or "").strip()
    if not clean or src_iso2 == dst_iso2:
        return ""
    qs = urllib.parse.urlencode({"q": clean, "langpair": f"{src_iso2}|{dst_iso2}"})
    try:
        data = _http_get_json(f"{_mymemory_url()}?{qs}")
    except (OSError, urllib.error.URLError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    tr_txt = str((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not tr_txt or "MYMEMORY WARNING" in tr_txt.upper():
        return ""
    if fold_ascii(tr_txt) == fold_ascii(clean):
        return ""
    return tr_txt


def lookup_free_dictionary(
    word: str,
    target_lang: str,
    meaning_lang: str,
) -> dict[str, str] | None:
    """Wiktionary + Tatoeba + MyMemory ile girişsiz/kotasız sözlük zenginleştirmesi."""
    clean_word = " ".join((word or "").strip().split())
    if not clean_word:
        return None
    src_iso2, src_iso3 = resolve_lang_codes(target_lang, ("en", "eng"))
    dst_iso2, dst_iso3 = resolve_lang_codes(meaning_lang, ("tr", "tur"))

    found_in_wikt = False
    pos = ""
    meanings: list[str] = []
    first_def = ""
    wikt_example = ""

    wikt_url = f"{_wiktionary_base()}/{urllib.parse.quote(src_iso2)}/{urllib.parse.quote(clean_word.lower())}?translations=true"
    try:
        wdata = _http_get_json(wikt_url)
    except (OSError, urllib.error.URLError, ValueError):
        wdata = None

    if isinstance(wdata, dict):
        entries = wdata.get("entries") or []
        if isinstance(entries, list) and entries:
            found_in_wikt = True
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not pos and entry.get("partOfSpeech"):
                    pos = normalize_pos(str(entry["partOfSpeech"]))
                for sense in entry.get("senses") or []:
                    if not isinstance(sense, dict):
                        continue
                    if not first_def and sense.get("definition"):
                        first_def = _clean_cell(sense["definition"])
                    if not wikt_example:
                        exs = sense.get("examples") or []
                        if exs and isinstance(exs[0], str):
                            cand_ex = _clean_cell(exs[0])
                            if 12 <= len(cand_ex) <= 180:
                                wikt_example = cand_ex
                    for tr_item in sense.get("translations") or []:
                        if not isinstance(tr_item, dict):
                            continue
                        lang_obj = tr_item.get("language") or {}
                        if lang_obj.get("code") == dst_iso2 and tr_item.get("word"):
                            w_tr = _clean_cell(tr_item["word"])
                            if w_tr and fold_ascii(w_tr) not in {fold_ascii(x) for x in meanings}:
                                meanings.append(w_tr)
                            if len(meanings) >= 4:
                                break

    # Tatoeba örnek cümle + çeviri çifti
    tatoeba_example = ""
    tatoeba_translation = ""
    tat_qs = urllib.parse.urlencode(
        {"from": src_iso3, "to": dst_iso3, "query": clean_word.lower()}
    )
    try:
        tdata = _http_get_json(f"{_tatoeba_url()}?{tat_qs}")
    except (OSError, urllib.error.URLError, ValueError):
        tdata = None

    if isinstance(tdata, dict):
        results = tdata.get("results") or []
        stem = clean_word.lower()[: max(3, len(clean_word) - 2)]
        for item in results:
            if not isinstance(item, dict):
                continue
            sent = _clean_cell(item.get("text") or "")
            if not sent or not (12 <= len(sent) <= 170):
                continue
            tr_groups = item.get("translations") or []
            tr_sent = ""
            for grp in tr_groups:
                if isinstance(grp, list) and grp and isinstance(grp[0], dict):
                    tr_sent = _clean_cell(grp[0].get("text") or "")
                    if tr_sent:
                        break
            if not tr_sent:
                continue
            if stem in sent.lower() or not tatoeba_example:
                tatoeba_example = sent
                tatoeba_translation = tr_sent
                if stem in sent.lower():
                    break

    meaning_str = ", ".join(meanings[:3])
    if not meaning_str and src_iso2 == dst_iso2 and first_def:
        meaning_str = first_def[:90]

    # Wiktionary kelimeyi tanıdıysa ama hedef dil çevirisi boşsa MyMemory ile tamamla
    if not meaning_str and (found_in_wikt or tatoeba_example):
        mm_word = _mymemory_translate(clean_word, src_iso2, dst_iso2)
        if mm_word:
            meaning_str = mm_word

    example_str = tatoeba_example or wikt_example
    translation_str = tatoeba_translation
    if example_str and not translation_str:
        translation_str = _mymemory_translate(example_str, src_iso2, dst_iso2)

    if not meaning_str and not example_str:
        return None

    return {
        "meaning": meaning_str,
        "pos": normalize_pos(pos, meaning_str),
        "example": example_str,
        "translation": translation_str,
    }


def _extract_json_object(raw_text: str) -> dict | None:
    txt = (raw_text or "").strip()
    if not txt:
        return None
    # ```json ... ``` çitlerini soy
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", txt, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        txt = fenced.group(1).strip()
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass
    start = txt.find("{")
    end = txt.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(txt[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            return None
    return None


def build_cli_command(provider: str, prompt: str, schema: dict, cwd: str) -> list[str]:
    if provider == "agy":
        return [
            find_bin("agy") or "agy",
            "--model",
            CLI_PROVIDERS["agy"]["model"],
            "--effort",
            "low",
            "--disable-slash-commands",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            f"-p={prompt}",
        ]
    if provider == "claude":
        return [
            find_bin("claude") or "claude",
            "-p",
            prompt,
            "--model",
            CLI_PROVIDERS["claude"]["model"],
            "--effort",
            "low",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            "--tools",
            "",
            "--no-session-persistence",
        ]
    if provider == "codex":
        Path(cwd, "schema.json").write_text(
            json.dumps({**schema, "additionalProperties": False}),
            encoding="utf-8",
        )
        return [
            find_bin("codex") or "codex",
            "exec",
            "-m",
            CLI_PROVIDERS["codex"]["model"],
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "-c",
            'model_reasoning_effort="low"',
            "--output-schema",
            "schema.json",
            "-o",
            "out.json",
            prompt,
        ]
    raise ValueError(f"Unsupported CLI provider: {provider}")


def _call_custom_v1(prompt: str, schema: dict, settings: dict, max_tokens: int = 350) -> dict | None:
    base_url = str(settings.get("customBaseUrl") or "").strip().rstrip("/")
    model = str(settings.get("customModel") or "").strip()
    if not base_url or not model:
        return None
    headers: dict[str, str] = {}
    api_key = read_custom_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    sys_msg = (
        "Reply ONLY with a single valid JSON object matching this JSON schema: "
        + json.dumps(schema)
    )
    body = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        resp = _http_post_json(f"{base_url}/chat/completions", body, headers=headers)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    if not isinstance(resp, dict):
        return None
    choices = resp.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    content = str(((choices[0].get("message") or {}).get("content")) or "")
    return _extract_json_object(content)


def call_ai_structured(
    prompt: str,
    schema: dict,
    settings: dict,
    runner=subprocess.run,
    max_tokens: int = 350,
) -> dict | None:
    provider = str(settings.get("aiProvider") or "off")
    if provider == "off":
        return None
    if provider == "custom":
        return _call_custom_v1(prompt, schema, settings, max_tokens=max_tokens)
    if provider not in CLI_PROVIDERS:
        return None

    with tempfile.TemporaryDirectory(prefix="lexis-ai-") as cwd:
        try:
            argv = build_cli_command(provider, prompt, schema, cwd)
            out = runner(
                argv,
                cwd=cwd,
                timeout=AI_TIMEOUT,
                capture_output=True,
                text=True,
                env=child_env(),
            )
            if provider == "agy":
                data = json.loads(out.stdout)
                ok = out.returncode == 0 and isinstance(data, dict) and data.get("status") == "SUCCESS"
                res = data.get("structured_output") if ok else None
                return res if isinstance(res, dict) else _extract_json_object(str(data.get("response") or ""))
            if provider == "claude":
                data = json.loads(out.stdout)
                ok = out.returncode == 0 and isinstance(data, dict) and data.get("is_error") is False
                res = data.get("structured_output") if ok else None
                return res if isinstance(res, dict) else _extract_json_object(str(data.get("result") or ""))
            if provider == "codex":
                out_file = Path(cwd, "out.json")
                if out.returncode == 0 and out_file.is_file():
                    res = json.loads(out_file.read_text(encoding="utf-8"))
                    return res if isinstance(res, dict) else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    return None


def ai_enrich_word(word: str, settings: dict, runner=subprocess.run) -> dict[str, str] | None:
    t_lang = settings["targetLang"]
    m_lang = settings["meaningLang"]
    prompt = (
        f"{t_lang} word or phrase: {json.dumps(word)}. "
        f"Provide its most common {m_lang} meaning(s) (comma-separated, concise), "
        f"part of speech (verb/noun/adjective/adverb/other), "
        f"one natural {t_lang} example sentence using it, and the {m_lang} translation of that sentence."
    )
    res = call_ai_structured(prompt, ENRICH_SCHEMA, settings, runner=runner)
    if not res:
        return None
    meaning = str(res.get("meaning") or "").strip()
    if not meaning:
        return None
    return {
        "meaning": meaning,
        "pos": normalize_pos(str(res.get("pos") or ""), meaning),
        "example": str(res.get("example") or "").strip(),
        "translation": str(res.get("translation") or "").strip(),
    }


def ai_judge_answer(
    word: str,
    meaning: str,
    typed_answer: str,
    settings: dict,
    runner=subprocess.run,
) -> bool | None:
    t_lang = settings["targetLang"]
    m_lang = settings["meaningLang"]
    prompt = (
        f"A learner studying {t_lang} was asked the {m_lang} meaning of {json.dumps(word)} "
        f"(reference meaning: {json.dumps(meaning)}). They answered {json.dumps(typed_answer)}. "
        f"Accept (accept: true) if it is a valid {m_lang} synonym/meaning with minor typos allowed; "
        "otherwise accept: false."
    )
    res = call_ai_structured(prompt, JUDGE_SCHEMA, settings, runner=runner)
    if res and isinstance(res.get("accept"), bool):
        return bool(res["accept"])
    return None


def candidate_word_for_translation(text: str, translation: str, source: str) -> str | None:
    clean_in = (text or "").strip()
    clean_out = (translation or "").strip()
    if not clean_in or "\n" in clean_in:
        return None
    if source == "target":
        tokens = clean_in.split()
        return clean_in if 1 <= len(tokens) <= 4 else None
    if "," in clean_in or len(clean_in.split()) > 2:
        return None
    first_chunk = clean_out.split(",")[0].strip()
    tokens = first_chunk.split()
    return first_chunk if 1 <= len(tokens) <= 4 else None


def hybrid_translate_text(text: str, settings: dict, runner=subprocess.run) -> dict | None:
    clean = (text or "").strip()
    if not clean:
        return None
    t_lang = settings["targetLang"]
    m_lang = settings["meaningLang"]

    if ai_can_run(settings):
        prompt = (
            f"Translate the text bidirectionally between {t_lang} (source='target') "
            f"and {m_lang} (source='meaning'). For a single word, give common comma-separated meanings. "
            f'Return JSON fields "translation" and "source". Text: {json.dumps(clean)}'
        )
        res = call_ai_structured(prompt, TRANSLATE_SCHEMA, settings, runner=runner)
        if res and str(res.get("translation") or "").strip() and res.get("source") in ("target", "meaning"):
            tr_txt = str(res["translation"]).strip()
            src = str(res["source"])
            return {
                "text": clean,
                "translation": tr_txt,
                "source": src,
                "via": "ai",
                "candidateWord": candidate_word_for_translation(clean, tr_txt, src),
            }

    # Ücretsiz sözlük + MyMemory çeviri katmanı
    src_iso2, _ = resolve_lang_codes(t_lang, ("en", "eng"))
    dst_iso2, _ = resolve_lang_codes(m_lang, ("tr", "tur"))

    if len(clean.split()) <= 2:
        d_fwd = lookup_free_dictionary(clean, t_lang, m_lang)
        if d_fwd and d_fwd.get("meaning"):
            m_txt = d_fwd["meaning"]
            return {
                "text": clean,
                "translation": m_txt,
                "source": "target",
                "via": "dictionary",
                "candidateWord": candidate_word_for_translation(clean, m_txt, "target"),
            }

    mm_fwd = _mymemory_translate(clean, src_iso2, dst_iso2)
    if mm_fwd:
        return {
            "text": clean,
            "translation": mm_fwd,
            "source": "target",
            "via": "dictionary",
            "candidateWord": candidate_word_for_translation(clean, mm_fwd, "target"),
        }

    mm_rev = _mymemory_translate(clean, dst_iso2, src_iso2)
    if mm_rev:
        return {
            "text": clean,
            "translation": mm_rev,
            "source": "meaning",
            "via": "dictionary",
            "candidateWord": candidate_word_for_translation(clean, mm_rev, "meaning"),
        }
    return None


def fetch_custom_models(base_url: str) -> list[str]:
    clean_base = (base_url or "").strip().rstrip("/")
    if not clean_base:
        return []
    headers: dict[str, str] = {}
    api_key = read_custom_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = _http_get_json(f"{clean_base}/models", headers=headers, timeout=HTTP_TIMEOUT)
    if not isinstance(data, dict):
        return []
    items = data.get("data") or data.get("models") or []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            mid = str(item.get("id") or item.get("name") or "").strip()
            if mid:
                out.append(mid)
    return out


# --- SQLite Depolama ve SRS ---


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
        resolved_pos = normalize_pos(pos, clean_meaning)
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

    def set_learned(self, word_ids: list[int], learned: bool) -> int:
        ids = [int(i) for i in word_ids]
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        cur = self.con.execute(f"UPDATE words SET hidden = ? WHERE id IN ({marks})", (LEARNED if learned else 0, *ids))
        self.con.commit()
        return cur.rowcount

    def delete_words(self, word_ids: list[int]) -> int:
        ids = [int(i) for i in word_ids]
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        self.con.execute(f"DELETE FROM events WHERE word_id IN ({marks})", ids)
        cur = self.con.execute(f"DELETE FROM words WHERE id IN ({marks})", ids)
        # Tamamen boşalan listeler de gider (silme eylemi yok, 0 kelimelik hayalet liste kalmasın); Custom kalır
        self.con.execute(
            "DELETE FROM lists WHERE name NOT IN ('Custom', 'Kendi')"
            " AND NOT EXISTS (SELECT 1 FROM words w WHERE w.list_id = lists.id)"
        )
        self.con.commit()
        return cur.rowcount

    def query_words(self, query: str = "", list_filter: str = "") -> list[Word]:
        if list_filter == "__hidden__":
            where, args = ["w.hidden = 1"], []
        elif list_filter == "__learned__":
            where, args = [f"w.hidden = {LEARNED}"], []
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

    def all_words_for_export(self) -> list[Word]:
        return self._words("1 = 1", (), "ORDER BY tr_lower(l.name), tr_lower(w.word), w.id")

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

    def new_words(self, limit: int, now: float | None = None) -> list[Word]:
        # Okunmadan atlanan tanışma kartı kelimeyi yeni bırakır ama due_at ile bir süre erteler
        return self._words(
            f"{ASKABLE_WHERE} AND w.box = -1 AND w.due_at <= ?",
            (float(time.time() if now is None else now), int(limit)),
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

    def recent_word_ids(self, limit: int, quizzed_only: bool = False) -> set[int]:
        where = "qtype != 'intro' AND result IN ('correct', 'wrong', 'skipped')" if quizzed_only else "result != 'hidden'"
        rows = self.con.execute(
            f"SELECT word_id FROM events WHERE {where} ORDER BY ts DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return {int(r[0]) for r in rows}

    def last_asked(self) -> dict[int, float]:
        return {int(w): float(t) for w, t in self.con.execute("SELECT word_id, MAX(ts) FROM events GROUP BY word_id")}

    def reviews_since_intro(self) -> int:
        return int(
            self.con.execute(
                "SELECT COUNT(*) FROM events WHERE result IN ('correct', 'wrong', 'skipped')"
                " AND ts > COALESCE((SELECT MAX(ts) FROM events WHERE result = 'intro'), 0)"
            ).fetchone()[0]
        )


def migrate_legacy_db(store: Store, legacy_file: Path) -> dict[str, int]:
    src = sqlite3.connect(str(legacy_file))
    try:
        src_lists: dict[int, str] = {}
        list_cols = {r[1] for r in src.execute("PRAGMA table_info(lists)")}
        has_source_col = "source" in list_cols
        list_query = (
            "SELECT id, name, COALESCE(enabled, 1), COALESCE(source, '') FROM lists"
            if has_source_col
            else "SELECT id, name, COALESCE(enabled, 1), '' FROM lists"
        )
        for lid, name, enabled, source in src.execute(list_query).fetchall():
            clean_name = "Custom" if name == "Kendi" else str(name or "Imported")
            src_lists[int(lid)] = clean_name
            store.ensure_list(clean_name)
            store.set_list_enabled(clean_name, bool(enabled))
            if source:
                store.set_list_source(clean_name, str(source))

        word_id_map: dict[int, int] = {}
        added_words = 0
        skipped_words = 0
        for row in src.execute(
            "SELECT id, word, COALESCE(meaning, ''), COALESCE(pos, ''), COALESCE(example, ''),"
            " COALESCE(translation, ''), COALESCE(list_id, 0), COALESCE(hidden, 0),"
            " COALESCE(enriched, 1), COALESCE(box, -1), COALESCE(due_at, 0), COALESCE(created_at, 0)"
            " FROM words"
        ).fetchall():
            old_id, wtxt, meaning, pos, ex, tr, lid, hid, enr, box, due, cts = row
            lname = src_lists.get(int(lid), "Custom")
            new_id = store.add_word(
                str(wtxt),
                meaning=str(meaning),
                pos=str(pos),
                example=str(ex),
                translation=str(tr),
                list_name=lname,
                enriched=bool(enr),
                box=int(box),
                due_at=float(due),
                hidden=bool(hid),
                created_at=float(cts or time.time()),
            )
            if new_id is not None:
                word_id_map[int(old_id)] = new_id
                added_words += 1
            else:
                skipped_words += 1

        added_events = 0
        if word_id_map:
            for old_wid, ts_val, qt, res, ans in src.execute(
                "SELECT word_id, ts, COALESCE(qtype, ''), COALESCE(result, ''), COALESCE(answer, '') FROM events"
            ).fetchall():
                mapped_id = word_id_map.get(int(old_wid))
                if mapped_id is not None:
                    canon_qt = LEGACY_QTYPE_MAP.get(str(qt), str(qt))
                    store.con.execute(
                        "INSERT INTO events(word_id, ts, qtype, result, answer) VALUES(?, ?, ?, ?, ?)",
                        (mapped_id, float(ts_val or time.time()), canon_qt, str(res), str(ans)),
                    )
                    added_events += 1
            store.con.commit()

        return {
            "addedWords": added_words,
            "skippedWords": skipped_words,
            "addedEvents": added_events,
        }
    finally:
        src.close()


def pick_word(store: Store, now: float) -> Word | None:
    """Sıradaki kelime: vadesi gelen tekrarlar önce, ama yeni kelimeler araya karışır ve son sorulanlar beklemeye alınır.

    Önceki hali hep en eski vadeli kelimeyi seçiyordu; birkaç kelime 10 dakikada bir vadeye girince
    aynı dörtlü dönüp duruyor, yeni kelimeler hiç tanıtılmıyordu.
    """
    due = store.due_words(now)
    fresh = store.new_words(1, now) if store.introduced_today(now) < NEW_PER_DAY else []
    if fresh and (not due or store.reviews_since_intro() >= REVIEWS_PER_NEW):
        return fresh[0]
    # Az önce tanıtılan kelime yalnız hemen ardından sorulmaz; tekrar engeli sorulmuş kelimelere uygulanır,
    # yoksa yeni destede ilk kartların hepsi tanışma olurdu.
    recent = store.recent_word_ids(1) | store.recent_word_ids(RECENT_GAP, quizzed_only=True)
    due_ok = [w for w in due if w.id not in recent]
    if due_ok:
        return due_ok[0]
    if fresh:
        return fresh[0]
    # Vadesi gelen ve yeni kelime yok: en uzun süredir sorulmayan kelime (vade sırası aynı birkaç kelimeyi döndürürdü)
    seen = [w for w in store.askable() if w.box >= 0]
    pool = [w for w in seen if w.id not in recent] or seen
    last = store.last_asked()
    return min(pool, key=lambda w: (last.get(w.id, 0.0), w.id)) if pool else None


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
        store.update_word(word.id, due_at=now + SKIP_DELAY)
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
    candidates.sort(key=lambda w: (w.pos != word.pos, w.list_id != word.list_id))
    chosen: list[Word] = []
    seen_labels = {own_label}
    seen_parts = set(own_parts)
    for w in candidates:
        lbl = fold_ascii(choice_label(w.meaning))
        w_parts = {fold_ascii(p) for p in meaning_parts(w.meaning) if fold_ascii(p)}
        if lbl and lbl not in seen_labels and not (seen_parts & w_parts):
            chosen.append(w)
            seen_labels.add(lbl)
            seen_parts.update(w_parts)
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
        "hidden": w.hidden == 1,
        "learned": w.hidden == LEARNED,
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
    # Öğrenilen kelimeler sorulmaz ama kelime hazinesinde kalır: toplama ve oturmuşlara sayılır
    settled_count = int(
        con.execute(
            "SELECT COUNT(*) FROM words WHERE hidden = ? OR (hidden = 0 AND box >= ?)",
            (LEARNED, SETTLED_BOX),
        ).fetchone()[0]
    )
    total_words = int(
        con.execute("SELECT COUNT(*) FROM words WHERE hidden IN (0, ?)", (LEARNED,)).fetchone()[0]
    )

    words_list = store.query_words(query=query, list_filter=list_filter)
    l5 = store.last5_map([w.id for w in words_list])
    words_out = [word_to_dict(w, last5=l5.get(w.id, [])) for w in words_list]

    selected_word = None
    # Seçili kelime silindiyse listenin ilk kelimesine düş (panel boş kalmasın)
    sw = store.get(selected_id) if selected_id > 0 else None
    if sw is None and words_list:
        sw = words_list[0]
    if sw:
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

        if cmd == "save-api-key":
            write_custom_api_key(str(payload.get("apiKey") or ""))
            return build_snapshot(store, settings, payload)

        if cmd == "clear-api-key":
            clear_custom_api_key()
            return build_snapshot(store, settings, payload)

        if cmd == "fetch-custom-models":
            base_url = str(payload.get("baseUrl") or settings["customBaseUrl"]).strip()
            try:
                models = fetch_custom_models(base_url)
                return {"ok": True, "models": models}
            except (OSError, urllib.error.URLError, ValueError) as exc:
                return {"ok": False, "error": str(exc), "models": []}

        if cmd == "login-cmd":
            prov = str(payload.get("provider") or settings["aiProvider"])
            meta = CLI_PROVIDERS.get(prov)
            if not meta:
                return {"ok": True, "argv": None}
            bin_path = find_bin(meta["bin"]) or meta["bin"]
            return {"ok": True, "argv": [bin_path, *meta["login_args"]]}

        if cmd == "test-ai":
            is_tr = settings["language"] == "tr"
            prov = settings["aiProvider"]
            if prov == "off":
                res = hybrid_translate_text("hello", settings)
                if res and res.get("translation"):
                    msg = (
                        f"Ücretsiz sözlük çalışıyor: hello → {res['translation']}"
                        if is_tr
                        else f"Free Dictionary ready: hello → {res['translation']}"
                    )
                    return {"ok": True, "connected": True, "message": msg}
                return {
                    "ok": True,
                    "connected": False,
                    "message": "Sözlük servisine ulaşılamadı." if is_tr else "Could not reach dictionary service.",
                }
            if prov in CLI_PROVIDERS:
                meta = CLI_PROVIDERS[prov]
                if not find_bin(meta["bin"]):
                    return {
                        "ok": True,
                        "connected": False,
                        "message": f"{meta['name']} kurulu değil ({meta['bin']})."
                        if is_tr
                        else f"{meta['name']} is not installed ({meta['bin']}).",
                    }
            if prov == "custom" and not ai_can_run(settings):
                return {
                    "ok": True,
                    "connected": False,
                    "message": "Base URL ve model adını girin." if is_tr else "Enter Base URL and model name.",
                }
            # Doğrudan AI çağrısını sına (yedek sözlüğe düşmeden)
            prompt = (
                f"Translate 'hello' between {settings['targetLang']} (source='target') "
                f"and {settings['meaningLang']} (source='meaning')."
            )
            ai_res = call_ai_structured(prompt, TRANSLATE_SCHEMA, settings)
            if ai_res and str(ai_res.get("translation") or "").strip():
                tr_out = str(ai_res["translation"]).strip()
                return {
                    "ok": True,
                    "connected": True,
                    "message": f"Bağlantı başarılı: hello → {tr_out}"
                    if is_tr
                    else f"Connected: hello → {tr_out}",
                }
            return {
                "ok": True,
                "connected": False,
                "message": "Sağlayıcı yanıt vermedi; giriş durumunu kontrol edin."
                if is_tr
                else "Provider did not respond; check login or endpoint.",
            }

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
                updates["pos"] = normalize_pos(str(payload["pos"]).strip())
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

        if cmd in ("set-learned", "delete-words"):
            ids = [int(i) for i in (payload.get("ids") or [])[:10000] if str(i).lstrip("-").isdigit()]
            if cmd == "set-learned":
                changed = store.set_learned(ids, bool(payload.get("learned", True)))
            else:
                changed = store.delete_words(ids)
            snap = build_snapshot(store, settings, payload)
            snap["changed"] = changed
            return snap

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

        if cmd == "preview-import":
            p = Path(str(payload.get("path") or "").strip()).expanduser()
            if not p.is_file():
                return {"ok": False, "error": f"File not found: {p}"}
            suf = p.suffix.lower()
            if suf in TEXT_SUFFIXES:
                rows, unparsed = read_text_import(p)
                # Önceki "AI ile oku" turlarının sonucu istemciden geri gelir; her tur sıradaki satırlardan devam eder.
                ai_rows = rows_from_payload(payload.get("aiRows"))
                ai_consumed = max(0, min(len(unparsed), int(payload.get("aiConsumed") or 0)))
                ai_failed = False
                if unparsed[ai_consumed:] and payload.get("useAi") and ai_can_run(settings):
                    new_rows, n_done = ai_parse_lines(unparsed[ai_consumed:], settings)
                    ai_failed = n_done == 0
                    ai_rows += new_rows
                    ai_consumed += n_done
                before = len(rows)
                rows = dedupe_rows(rows + ai_rows)
                ai_added = len(rows) - before
                unparsed = unparsed[ai_consumed:]
                existing = {word_key(w.word) for w in store.all_words_for_export()}
                return {
                    "ok": True,
                    "path": str(p),
                    "kind": suf.lstrip("."),
                    "name": default_list_name_for(p),
                    "total": len(rows),
                    "rows": [r.to_dict() for r in rows],
                    "raw": [],
                    "unparsed": len(unparsed),
                    "unparsedSample": unparsed[:5],
                    "duplicates": sum(1 for r in rows if word_key(r.word) in existing),
                    "aiAdded": ai_added,
                    "aiRows": [r.to_dict() for r in ai_rows],
                    "aiConsumed": ai_consumed,
                    "aiFailed": ai_failed,
                    "aiAvailable": ai_can_run(settings),
                }
            cols = _normalize_columns(payload.get("columns"))
            rows = read_import_rows(p, columns=cols)
            return {
                "ok": True,
                "path": str(p),
                "kind": "csv",
                "name": default_list_name_for(p),
                "total": len(rows),
                "rows": [r.to_dict() for r in rows[:10]],
                "raw": read_csv_raw(p, limit=10),
            }

        if cmd == "confirm-import":
            p = Path(str(payload.get("path") or "").strip()).expanduser()
            cols = _normalize_columns(payload.get("columns"))
            res = import_file_into_store(
                store,
                p,
                list_name=str(payload.get("listName") or "").strip() or None,
                columns=cols,
                # Önizlemede (AI dahil) çözülen satırlar aynen eklenir; dosya ikinci kez çözülmez.
                rows=rows_from_payload(payload["rows"]) if isinstance(payload.get("rows"), list) else None,
            )
            if not res.get("ok"):
                return res
            snap = build_snapshot(store, settings, payload)
            snap.update(res)
            return snap

        if cmd == "load-starter":
            sp = starter_csv_path()
            res = import_file_into_store(store, sp, list_name="Starter Deck")
            if not res.get("ok"):
                return res
            snap = build_snapshot(store, settings, payload)
            snap.update(res)
            return snap

        if cmd == "import-legacy":
            lp_str = str(payload.get("path") or "").strip()
            lp = Path(lp_str).expanduser() if lp_str else legacy_db_path()
            if not lp.is_file():
                return {"ok": False, "error": f"Legacy database not found: {lp}"}
            counts = migrate_legacy_db(store, lp)
            snap = build_snapshot(store, settings, payload)
            snap.update(counts)
            return snap

        if cmd == "export-csv":
            out_p = Path(str(payload.get("path") or "").strip()).expanduser()
            if not str(out_p):
                return {"ok": False, "error": "Missing export path"}
            out_p.parent.mkdir(parents=True, exist_ok=True)
            all_words = store.all_words_for_export()
            with out_p.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["word", "meaning", "example", "translation", "list", "box", "hidden"])
                for w in all_words:
                    writer.writerow(
                        [w.word, w.meaning, w.example, w.translation, w.list_name, w.box, w.hidden]
                    )
            return {"ok": True, "count": len(all_words), "path": str(out_p)}

        if cmd == "enrich-word":
            wid = int(payload.get("wordId") or 0)
            # İçe aktarma sonrası arka plan zenginleştirmesi kullanıcının seçili kelimesini değiştirmez.
            sel_payload = payload if payload.get("background") else {**payload, "selectedWordId": wid}
            initial = store.get(wid)
            if not initial:
                return {"ok": False, "error": "Word not found"}
            if initial.enriched and initial.meaning.strip():
                hist = store.full_history(initial.id, answered_only=True)
                snap = build_snapshot(store, settings, sel_payload)
                snap.update(
                    {
                        "wordId": wid,
                        "enriched": True,
                        "via": "none",
                        "word": word_to_dict(initial, last5=hist[-5:], history=hist),
                    }
                )
                return snap

            dict_res = (
                lookup_free_dictionary(initial.word, settings["targetLang"], settings["meaningLang"])
                if settings.get("dictionaryEnabled", True)
                else None
            )
            meaning = (dict_res or {}).get("meaning", "").strip()
            pos = (dict_res or {}).get("pos", "").strip()
            example = (dict_res or {}).get("example", "").strip()
            translation = (dict_res or {}).get("translation", "").strip()
            used_dict = bool(meaning or example)
            used_ai = False

            need_ai = (not meaning or not example or not translation) and ai_can_run(settings)
            if need_ai:
                ai_res = ai_enrich_word(initial.word, settings)
                if ai_res:
                    used_ai = True
                    if not meaning and ai_res.get("meaning"):
                        meaning = ai_res["meaning"]
                    if (not pos or pos == "other") and ai_res.get("pos"):
                        pos = ai_res["pos"]
                    if not example and ai_res.get("example"):
                        example = ai_res["example"]
                        translation = ai_res.get("translation", "")
                    elif example and not translation and ai_res.get("translation") and not ai_res.get("example"):
                        translation = ai_res["translation"]

            # Kirli düzenleme koruması: çağrı sürerken kullanıcının yazdığı alanları ezme
            fresh = store.get(wid)
            if not fresh:
                return {"ok": False, "error": "Word removed during enrichment"}

            updates: dict[str, object] = {}
            if not fresh.enriched and not fresh.meaning.strip() and meaning:
                updates["meaning"] = meaning
                updates["pos"] = normalize_pos(pos, meaning)
                updates["enriched"] = 1

            if not fresh.example.strip() and example:
                updates["example"] = example
                if not fresh.translation.strip() and translation:
                    updates["translation"] = translation
                if fresh.meaning.strip():
                    updates["enriched"] = 1
            # Sözlük ve AI anlam bulamadıysa arama bitti sayılır: arayüz "aranıyor" yerine "bulunamadı" gösterir.
            if not fresh.enriched and not fresh.meaning.strip() and not meaning:
                updates["enriched"] = 1

            if updates:
                store.update_word(wid, **updates)

            after = store.get(wid) or fresh
            via = (
                "hybrid"
                if (used_dict and used_ai and updates)
                else "dictionary"
                if (used_dict and updates)
                else "ai"
                if (used_ai and updates)
                else "none"
            )
            hist = store.full_history(after.id, answered_only=True)
            snap = build_snapshot(store, settings, sel_payload)
            snap.update(
                {
                    "wordId": wid,
                    "enriched": bool(after.enriched),
                    "via": via,
                    "word": word_to_dict(after, last5=hist[-5:], history=hist),
                }
            )
            return snap

        if cmd == "judge-answer":
            now = float(payload.get("now") or time.time())
            wid = int(payload.get("wordId") or 0)
            qtype = str(payload.get("qtype") or "type_word_meaning")
            typed = str(payload.get("typedText") or "").strip()
            word = store.get(wid)
            if not word:
                return {"ok": False, "error": "Word not found"}
            accepted = bool(ai_judge_answer(word.word, word.meaning, typed, settings))
            res_kind = "correct" if accepted else "wrong"
            apply_srs(store, word, res_kind, now, qtype=qtype, answer=typed)
            snap = build_snapshot(store, settings, payload)
            snap.update(
                {
                    "status": "recorded",
                    "result": res_kind,
                    "feedback": build_feedback(word, qtype, accepted),
                }
            )
            return snap

        if cmd == "translate-text":
            txt = str(payload.get("text") or "").strip()
            if not txt:
                return {"ok": False, "error": "Empty text"}
            tr_res = hybrid_translate_text(txt, settings)
            if not tr_res:
                return {
                    "ok": False,
                    "error": "Çeviri alınamadı."
                    if settings["language"] == "tr"
                    else "Could not translate text.",
                }
            return {"ok": True, **tr_res}

        if cmd == "next-question":
            now = float(payload.get("now") or time.time())
            rep = payload.get("replaceQuestion")
            if isinstance(rep, dict) and rep.get("wordId"):
                prev_word = store.get(int(rep["wordId"]))
                if prev_word:
                    prev_qt = str(rep.get("qtype") or "")
                    # Okunmadan değiştirilen tanışma kartı öğrenildi sayılmaz: kelime yeni kalır, ertelenir
                    apply_srs(store, prev_word, "skipped", now, qtype=prev_qt)
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
                # ✕/Esc tanışma kartında da "şimdi değil" demektir: kelime yeni kalır, yarım saat sonra yeniden tanıtılır
                res_kind = "skipped"
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
