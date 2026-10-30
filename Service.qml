import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import qs.Commons
import qs.Commons as Commons
import "Bridge.js" as Bridge
import "Theme.js" as Theme
import "windows"

// omarchy-shell içinde çalışan Lexis arka plan servisi.
// Zamanlayıcıyı, sağ üst soru bildirim kartını, Python SQLite/SRS/hibrit sözlük RPC kuyruğunu,
// seçili metin yakalamayı (wl-paste) ve `omarchy-shell lexis ...` IPC komutlarını yönetir.
Item {
  id: svcRoot

  property var shell: null
  property var manifest: null
  property var mainPanelRef: mainPanelWin

  property var settings: ({
    language: "en",
    themeMode: "omarchy",
    toastScreen: "",
    intervalMin: 5,
    dailyGoal: 50,
    targetLang: "English",
    meaningLang: "Turkish",
    dictionaryEnabled: true,
    aiProvider: "off",
    customBaseUrl: "http://127.0.0.1:11434/v1",
    customModel: "",
    mutedUntil: 0
  })

  readonly property string lang: settings && settings.language === "tr" ? "tr" : "en"
  readonly property var tokens: Theme.resolveTokens(
    settings && settings.themeMode ? String(settings.themeMode) : "omarchy",
    Commons.Color.background,
    Commons.Color.foreground,
    Commons.Color.accent,
    Commons.Color.urgent
  )

  property string dbPath: "~/.local/share/lexis/lexis.sqlite"
  property bool hasCustomApiKey: false
  property var todayData: ({ answered: 0, goal: 50, nextInMin: 5, mutedUntil: 0, recent: [], totalWords: 0 })
  property var statsData: ({ answeredToday: 0, accuracy: 0, settled: 0, totalWords: 0, hardest: [], days: [], byType: ({}) })
  property var listsData: []
  property var wordsData: []
  property var selectedWord: null
  property var providers: []
  property var customModels: []
  property bool legacyAvailable: false

  // Kelimeler sekmesi filtre durumu
  property string wordsQuery: ""
  property string wordsListFilter: ""
  property int selectedWordId: 0

  // Aktif sağ üst soru ve geri bildirim durumu
  property var activeQuestion: null
  property var feedbackToast: null
  property bool judging: false
  property bool translating: false
  property int _translateReqSeq: 0
  property var lastTranslation: null
  property string aiTestStatus: ""
  property string statusNotice: ""
  property bool nativeDialogOpen: false

  // Zamanlayıcı durumu
  property real _lastQuizEpoch: Math.floor(Date.now() / 1000)
  property int nextInSeconds: 300
  readonly property bool isMuted: {
    var mu = settings && settings.mutedUntil ? Number(settings.mutedUntil) : 0
    return mu > Math.floor(Date.now() / 1000)
  }

  readonly property string backendScriptPath: {
    var u = String(Qt.resolvedUrl("backend/lexis_cli.py"))
    return u.indexOf("file://") === 0 ? decodeURIComponent(u.slice(7)) : u
  }

  Component.onCompleted: {
    Bridge.registerService(svcRoot)
    _lastQuizEpoch = Math.floor(Date.now() / 1000)
    _recomputeCountdown()
    refreshSnapshot(null)
  }

  Component.onDestruction: {
    Bridge.unregisterService(svcRoot)
  }

  // --- Omarchy Kilit & Rahatsız Etme (DND) Algılama ---
  function _isSystemPaused() {
    if (shell && typeof shell.serviceFor === "function") {
      var lockSvc = shell.serviceFor("omarchy.lock")
      if (lockSvc) {
        if (typeof lockSvc.currentlyLocked === "function" && lockSvc.currentlyLocked()) return true
        if (lockSvc.locked) return true
      }
      var notifSvc = shell.serviceFor("omarchy.notifications")
      if (notifSvc && notifSvc.doNotDisturb) return true
    }
    return false
  }

  function _intervalSeconds() {
    var m = settings && settings.intervalMin ? Number(settings.intervalMin) : 5
    return Math.max(60, Math.min(3600, Math.round(m) * 60))
  }

  function _recomputeCountdown() {
    var nowSec = Math.floor(Date.now() / 1000)
    var mu = settings && settings.mutedUntil ? Number(settings.mutedUntil) : 0
    if (mu > nowSec) {
      nextInSeconds = Math.max(0, Math.round(mu - nowSec))
      return
    }
    var rem = (_lastQuizEpoch + _intervalSeconds()) - nowSec
    nextInSeconds = Math.max(0, Math.round(rem))
  }

  Timer {
    id: quizTimer
    interval: 15000
    running: true
    repeat: true
    onTriggered: {
      var nowSec = Math.floor(Date.now() / 1000)
      var mu = svcRoot.settings && svcRoot.settings.mutedUntil ? Number(svcRoot.settings.mutedUntil) : 0
      var dec = Bridge.decideQuizTick(
        nowSec,
        svcRoot._lastQuizEpoch,
        svcRoot._intervalSeconds(),
        mu,
        svcRoot._isSystemPaused(),
        svcRoot.activeQuestion !== null,
        toastWin.inputActive,
        svcRoot.judging
      )
      if (dec.action === "draw") {
        svcRoot._drawScheduledQuestion()
      } else {
        svcRoot._lastQuizEpoch = dec.nextLastEpoch
        svcRoot._recomputeCountdown()
      }
    }
  }

  Timer {
    id: countdownTick
    interval: 5000
    running: true
    repeat: true
    onTriggered: svcRoot._recomputeCountdown()
  }

  // --- Birincil Hızlı RPC Kuyruğu (SQLite & SRS) ---
  property var _rpcQueue: []
  property bool _rpcBusy: false
  property var _currentRpc: null

  function _queryStatePayload(extra) {
    var p = {
      query: svcRoot.wordsQuery,
      listFilter: svcRoot.wordsListFilter,
      selectedWordId: svcRoot.selectedWordId
    }
    if (extra) {
      for (var k in extra) p[k] = extra[k]
    }
    return p
  }

  function enqueueRpc(cmd, payload, onDone) {
    _rpcQueue.push({ cmd: cmd, payload: payload || ({}), onDone: onDone || null })
    _pumpRpc()
  }

  function _pumpRpc() {
    if (_rpcBusy || _rpcQueue.length === 0) return
    _rpcBusy = true
    _currentRpc = _rpcQueue.shift()
    rpcProcess.stdinEnabled = true
    rpcProcess.command = ["python3", svcRoot.backendScriptPath, _currentRpc.cmd, "-"]
    rpcProcess.running = true
    rpcProcess.write(JSON.stringify(_currentRpc.payload) + "\n")
    rpcProcess.stdinEnabled = false
  }

  function _applySnapshot(res) {
    if (!res || !res.ok) return
    if (res.dbPath) svcRoot.dbPath = String(res.dbPath)
    if (res.settings) svcRoot.settings = res.settings
    if (res.hasCustomApiKey !== undefined) svcRoot.hasCustomApiKey = !!res.hasCustomApiKey
    if (res.today) svcRoot.todayData = res.today
    if (res.stats) svcRoot.statsData = res.stats
    if (res.lists) svcRoot.listsData = res.lists
    if (res.words) svcRoot.wordsData = res.words
    if (res.selectedWord !== undefined) {
      svcRoot.selectedWord = res.selectedWord
      if (res.selectedWord && res.selectedWord.id) {
        svcRoot.selectedWordId = Number(res.selectedWord.id)
      }
    }
    if (res.legacyAvailable !== undefined) svcRoot.legacyAvailable = !!res.legacyAvailable
    if (res.providers) svcRoot.providers = res.providers
    svcRoot._recomputeCountdown()
  }

  Process {
    id: rpcProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var job = svcRoot._currentRpc
        svcRoot._currentRpc = null
        svcRoot._rpcBusy = false
        var parsed = null
        var raw = String(text || "").trim()
        if (raw.length > 0) {
          try { parsed = JSON.parse(raw) } catch (e) { parsed = null }
        }
        if (parsed && parsed.ok) {
          svcRoot._applySnapshot(parsed)
        }
        if (job && job.onDone) {
          try { job.onDone(parsed) } catch (e2) {}
        }
        svcRoot._pumpRpc()
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && svcRoot._rpcBusy) {
        var failedJob = svcRoot._currentRpc
        svcRoot._currentRpc = null
        svcRoot._rpcBusy = false
        if (failedJob && failedJob.onDone) {
          try { failedJob.onDone(null) } catch (e3) {}
        }
        svcRoot._pumpRpc()
      }
    }
  }

  // --- İkincil Ağ/AI Arka Plan Kuyruğu (enrich, judge, translate, test-ai) ---
  property var _bgQueue: []
  property bool _bgBusy: false
  property var _currentBg: null

  function enqueueBgRpc(cmd, payload, onDone) {
    _bgQueue.push({ cmd: cmd, payload: payload || ({}), onDone: onDone || null })
    _pumpBg()
  }

  function _pumpBg() {
    if (_bgBusy || _bgQueue.length === 0) return
    _bgBusy = true
    _currentBg = _bgQueue.shift()
    bgProcess.stdinEnabled = true
    bgProcess.command = ["python3", svcRoot.backendScriptPath, _currentBg.cmd, "-"]
    bgProcess.running = true
    bgProcess.write(JSON.stringify(_currentBg.payload) + "\n")
    bgProcess.stdinEnabled = false
  }

  Process {
    id: bgProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var job = svcRoot._currentBg
        svcRoot._currentBg = null
        svcRoot._bgBusy = false
        var parsed = null
        var raw = String(text || "").trim()
        if (raw.length > 0) {
          try { parsed = JSON.parse(raw) } catch (e) { parsed = null }
        }
        if (parsed && parsed.ok && parsed.settings) {
          svcRoot._applySnapshot(parsed)
        }
        if (job && job.onDone) {
          try { job.onDone(parsed) } catch (e2) {}
        }
        svcRoot._pumpBg()
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && svcRoot._bgBusy) {
        var failedJob = svcRoot._currentBg
        svcRoot._currentBg = null
        svcRoot._bgBusy = false
        if (failedJob && failedJob.onDone) {
          try { failedJob.onDone(null) } catch (e3) {}
        }
        svcRoot._pumpBg()
      }
    }
  }

  // --- Kamu Yöntemleri (Bar, Toast ve 6 Sayfa Tarafından Tüketilir) ---

  function refreshSnapshot(opts) {
    if (opts) {
      if (opts.query !== undefined) wordsQuery = String(opts.query)
      if (opts.listFilter !== undefined) wordsListFilter = String(opts.listFilter)
      if (opts.selectedWordId !== undefined) selectedWordId = Number(opts.selectedWordId) || 0
    }
    enqueueRpc("snapshot", _queryStatePayload(null), null)
  }

  function saveSettings(patch) {
    enqueueRpc("save-settings", _queryStatePayload(patch || ({})), function() {
      svcRoot._recomputeCountdown()
    })
  }

  function _drawScheduledQuestion() {
    var payload = {}
    if (activeQuestion && activeQuestion.wordId) {
      payload.replaceQuestion = {
        wordId: Number(activeQuestion.wordId),
        qtype: String(activeQuestion.qtype || "")
      }
    }
    _lastQuizEpoch = Math.floor(Date.now() / 1000)
    _recomputeCountdown()
    enqueueRpc("next-question", payload, function(res) {
      if (res && res.ok && res.question) {
        svcRoot.judging = false
        svcRoot.feedbackToast = null
        svcRoot.activeQuestion = res.question
      }
    })
  }

  function askNow(wordId) {
    var payload = {}
    var wid = Number(wordId) || 0
    if (wid > 0) payload.wordId = wid
    if (activeQuestion && activeQuestion.wordId) {
      payload.replaceQuestion = {
        wordId: Number(activeQuestion.wordId),
        qtype: String(activeQuestion.qtype || "")
      }
    }
    _lastQuizEpoch = Math.floor(Date.now() / 1000)
    _recomputeCountdown()
    enqueueRpc("next-question", payload, function(res) {
      if (res && res.ok && res.question) {
        svcRoot.judging = false
        svcRoot.feedbackToast = null
        svcRoot.activeQuestion = res.question
      } else {
        svcRoot.showInfoToast(
          "Lexis",
          Theme.t(svcRoot.lang, "Sorulacak kelime yok — önce liste veya kelime ekle.", "No askable words yet — import a deck or add a word.")
        )
      }
    })
  }

  function ackIntro() {
    if (!activeQuestion) return
    var q = activeQuestion
    activeQuestion = null
    enqueueRpc("grade-question", _queryStatePayload({
      wordId: q.wordId,
      qtype: "intro",
      action: "intro"
    }), null)
  }

  function skipCurrent() {
    if (!activeQuestion) return
    var q = activeQuestion
    activeQuestion = null
    judging = false
    enqueueRpc("grade-question", _queryStatePayload({
      wordId: q.wordId,
      qtype: q.qtype,
      action: "skip"
    }), null)
  }

  function hideCurrentWord() {
    if (!activeQuestion) return
    var q = activeQuestion
    activeQuestion = null
    judging = false
    enqueueRpc("grade-question", _queryStatePayload({
      wordId: q.wordId,
      qtype: q.qtype,
      action: "hide"
    }), null)
  }

  function submitChoice(index) {
    if (!activeQuestion || judging) return
    var q = activeQuestion
    enqueueRpc("grade-question", _queryStatePayload({
      wordId: q.wordId,
      qtype: q.qtype,
      action: "choice",
      choiceIndex: Number(index),
      correctIndex: Number(q.correctIndex),
      choiceText: (q.choices && q.choices[index]) ? String(q.choices[index]) : ""
    }), function(res) {
      svcRoot.activeQuestion = null
      if (res && res.feedback) svcRoot.feedbackToast = res.feedback
    })
  }

  function submitTyped(text) {
    if (!activeQuestion || judging) return
    var q = activeQuestion
    var clean = String(text || "").trim()
    if (!clean) {
      skipCurrent()
      return
    }
    judging = true
    enqueueRpc("grade-question", _queryStatePayload({
      wordId: q.wordId,
      qtype: q.qtype,
      action: "typed",
      typedText: clean
    }), function(res) {
      if (!res || !res.ok) {
        svcRoot.judging = false
        svcRoot.activeQuestion = null
        return
      }
      if (res.status === "needs_ai_judge") {
        svcRoot.enqueueBgRpc("judge-answer", svcRoot._queryStatePayload({
          wordId: q.wordId,
          qtype: q.qtype,
          typedText: clean
        }), function(jres) {
          svcRoot.judging = false
          svcRoot.activeQuestion = null
          if (jres && jres.feedback) svcRoot.feedbackToast = jres.feedback
        })
      } else {
        svcRoot.judging = false
        svcRoot.activeQuestion = null
        if (res.feedback) svcRoot.feedbackToast = res.feedback
      }
    })
  }

  function clearFeedback() {
    feedbackToast = null
  }

  function showInfoToast(badge, headline) {
    if (activeQuestion !== null) return
    feedbackToast = {
      infoOnly: true,
      badge: String(badge || "Lexis"),
      headline: String(headline || ""),
      exampleHtml: ""
    }
  }

  function focusToastInput() {
    toastWin.focusInput()
  }

  function addWordQuick(wordText, cb) {
    var clean = String(wordText || "").trim()
    if (!clean) return
    enqueueRpc("add-word", _queryStatePayload({ word: clean, listName: "Custom" }), function(res) {
      if (res && res.ok) {
        if (res.needsEnrich && res.wordId) {
          svcRoot.enqueueBgRpc("enrich-word", svcRoot._queryStatePayload({ wordId: res.wordId }), null)
        }
        if (cb) cb(res)
      }
    })
  }

  function addManualWord(payload, cb) {
    enqueueRpc("add-word", _queryStatePayload(payload || ({})), function(res) {
      if (res && res.ok && res.needsEnrich && res.wordId) {
        svcRoot.enqueueBgRpc("enrich-word", svcRoot._queryStatePayload({ wordId: res.wordId }), null)
      }
      if (cb) cb(res)
    })
  }

  function updateWord(payload, cb) {
    enqueueRpc("update-word", _queryStatePayload(payload || ({})), function(res) {
      if (cb) cb(res)
    })
  }

  function setWordHidden(wordId, hidden) {
    enqueueRpc("set-hidden", _queryStatePayload({ wordId: Number(wordId), hidden: !!hidden }), null)
  }

  function setListEnabled(name, enabled) {
    enqueueRpc("set-list-enabled", _queryStatePayload({ name: String(name), enabled: !!enabled }), null)
  }

  function loadListWords(name, cb) {
    enqueueRpc("list-words", { name: String(name || "") }, function(res) {
      if (cb && res && res.ok) cb(res.words || [])
    })
  }

  function openSourceFile(sourcePath) {
    var p = String(sourcePath || "").trim()
    if (p) Quickshell.execDetached(["xdg-open", p])
  }

  // --- Seçili Metinden Hızlı Kelime Yakalama (`SUPER + SHIFT + X`) ---
  function _handleCapturedClipboardText(rawText) {
    var line = String(rawText || "").replace(/\r/g, " ").split("\n")[0].trim()
    line = line.replace(/^["'“”‘’([{<]+|["'“”‘’)\]}>.,;:!?]+$/g, "").trim()
    if (!line || line.length > 64 || line.split(/\s+/).length > 5) {
      showInfoToast(
        "Lexis",
        Theme.t(lang, "Geçerli bir kelime seçili değil.", "No short word or phrase selected.")
      )
      return
    }
    enqueueRpc("add-word", _queryStatePayload({ word: line, listName: "Custom" }), function(res) {
      if (!res || !res.ok) return
      if (res.duplicate) {
        svcRoot.showInfoToast(
          "Lexis",
          Theme.t(svcRoot.lang, "Zaten listede: ", "Already in deck: ") + line
        )
      } else {
        svcRoot.showInfoToast(
          "Lexis",
          Theme.t(svcRoot.lang, "Eklendi: ", "Added: ") + line
        )
      }
      if (res.needsEnrich && res.wordId) {
        svcRoot.enqueueBgRpc("enrich-word", svcRoot._queryStatePayload({ wordId: res.wordId }), null)
      }
    })
  }

  Process {
    id: primaryClipProc
    command: ["wl-paste", "--primary", "--no-newline"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var txt = String(text || "").trim()
        if (txt.length > 0) svcRoot._handleCapturedClipboardText(txt)
        else fallbackClipProc.running = true
      }
    }
    onExited: function(code) {
      if (code !== 0 && !fallbackClipProc.running) fallbackClipProc.running = true
    }
  }

  Process {
    id: fallbackClipProc
    command: ["wl-paste", "--no-newline"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: svcRoot._handleCapturedClipboardText(text)
    }
  }

  function addSelection() {
    if (!primaryClipProc.running && !fallbackClipProc.running) {
      primaryClipProc.running = true
    }
  }

  // --- Dosya Seçici (zenity) & İçe/Dışa Aktarma ---
  property var _importDialogCb: null

  Process {
    id: importPickerProc
    command: [
      "zenity",
      "--file-selection",
      "--title=Import Vocabulary List",
      "--file-filter=Word lists (csv tsv pdf docx odt txt md) | *.csv *.CSV *.tsv *.TSV *.pdf *.PDF *.docx *.DOCX *.odt *.ODT *.txt *.TXT *.md",
      "--file-filter=All files | *"
    ]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        svcRoot.nativeDialogOpen = false
        var chosen = String(text || "").trim()
        var cb = svcRoot._importDialogCb
        svcRoot._importDialogCb = null
        if (chosen && cb) cb(chosen)
      }
    }
    onExited: function(code) {
      if (code !== 0) {
        svcRoot.nativeDialogOpen = false
        svcRoot._importDialogCb = null
      }
    }
  }

  Process {
    id: exportPickerProc
    command: [
      "zenity",
      "--file-selection",
      "--save",
      "--confirm-overwrite",
      "--filename=lexis-words.csv",
      "--title=Export Lexis Vocabulary (CSV)"
    ]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        svcRoot.nativeDialogOpen = false
        var outPath = String(text || "").trim()
        if (outPath) {
          svcRoot.enqueueRpc("export-csv", { path: outPath }, function(res) {
            if (res && res.ok) {
              svcRoot.statusNotice = Theme.t(svcRoot.lang, "Dışa aktarıldı: ", "Exported: ") + res.count
            }
          })
        }
      }
    }
    onExited: function(code) {
      if (code !== 0) svcRoot.nativeDialogOpen = false
    }
  }

  function openImportDialog(cb) {
    if (importPickerProc.running) return
    _importDialogCb = cb || null
    nativeDialogOpen = true
    importPickerProc.running = true
  }

  function previewImport(path, cols, cb, useAi) {
    enqueueRpc("preview-import", { path: String(path || ""), columns: cols || [0, 1, 2, 3], useAi: !!useAi }, function(res) {
      if (cb) cb(res)
    })
  }

  // rows verilirse (CSV dışı önizleme, AI dahil) backend dosyayı yeniden çözmeden aynen ekler.
  function confirmImport(path, listName, cols, cb, rows) {
    var payload = { path: String(path || ""), listName: String(listName || ""), columns: cols || [0, 1, 2, 3] }
    if (rows) payload.rows = rows
    enqueueRpc("confirm-import", _queryStatePayload(payload), function(res) {
      if (cb) cb(res)
    })
  }

  function loadStarterDeck(cb) {
    enqueueRpc("load-starter", _queryStatePayload(null), function(res) {
      if (res && res.ok) {
        svcRoot.statusNotice = Theme.t(svcRoot.lang, "Başlangıç destesi yüklendi: +", "Starter deck loaded: +") + res.added
      }
      if (cb) cb(res)
    })
  }

  function importLegacyDb() {
    enqueueRpc("import-legacy", _queryStatePayload(null), function(res) {
      if (res && res.ok) {
        svcRoot.statusNotice = Theme.t(svcRoot.lang, "Eski Kelime verisi aktarıldı: +", "Imported legacy Kelime words: +") + (res.addedWords || 0)
      }
    })
  }

  function exportCsvDialog() {
    if (exportPickerProc.running) return
    nativeDialogOpen = true
    exportPickerProc.running = true
  }

  // --- Hibrit Çeviri, Özel /v1 Modeller, 0600 Anahtar ve AI Girişi ---

  function translateText(text) {
    var clean = String(text || "").trim()
    if (!clean) return
    _translateReqSeq += 1
    var reqId = _translateReqSeq
    translating = true
    enqueueBgRpc("translate-text", { text: clean }, function(res) {
      if (reqId !== svcRoot._translateReqSeq) return
      svcRoot.translating = false
      if (res && res.ok) {
        svcRoot.lastTranslation = res
      } else {
        svcRoot.lastTranslation = {
          error: (res && res.error) ? String(res.error) : Theme.t(svcRoot.lang, "Çeviri alınamadı.", "Translation unavailable.")
        }
      }
    })
  }

  function fetchCustomModels(baseUrl, cb) {
    enqueueBgRpc("fetch-custom-models", { baseUrl: String(baseUrl || "") }, function(res) {
      if (res && res.ok && res.models) svcRoot.customModels = res.models
      if (cb) cb(res)
    })
  }

  function saveCustomApiKey(apiKey, cb) {
    enqueueRpc("save-api-key", _queryStatePayload({ apiKey: String(apiKey || "") }), function(res) {
      if (cb) cb(res)
    })
  }

  function clearCustomApiKey(cb) {
    enqueueRpc("clear-api-key", _queryStatePayload(null), function(res) {
      if (cb) cb(res)
    })
  }

  function testAiConnection() {
    aiTestStatus = Theme.t(lang, "Deneniyor…", "Testing…")
    enqueueBgRpc("test-ai", {}, function(res) {
      if (res && res.message) svcRoot.aiTestStatus = String(res.message)
      else svcRoot.aiTestStatus = Theme.t(svcRoot.lang, "Yanıt alınamadı.", "No response.")
    })
  }

  function openAiLogin(provider) {
    enqueueRpc("login-cmd", { provider: String(provider || "") }, function(res) {
      if (!res || !res.ok || !res.argv || res.argv.length === 0) return
      var cmdParts = []
      for (var i = 0; i < res.argv.length; i++) {
        var part = String(res.argv[i]).replace(/'/g, "'\\''")
        cmdParts.push("'" + part + "'")
      }
      var shellLine = cmdParts.join(" ") + "; printf '\\nPress Enter to close...'; read _"
      Quickshell.execDetached([
        "sh",
        "-c",
        "if command -v xdg-terminal-exec >/dev/null 2>&1; then exec xdg-terminal-exec sh -c \"$1\"; " +
        "elif command -v ghostty >/dev/null 2>&1; then exec ghostty -e sh -c \"$1\"; " +
        "elif command -v alacritty >/dev/null 2>&1; then exec alacritty -e sh -c \"$1\"; " +
        "elif command -v kitty >/dev/null 2>&1; then exec kitty sh -c \"$1\"; " +
        "elif command -v foot >/dev/null 2>&1; then exec foot sh -c \"$1\"; fi",
        "lexis-login",
        shellLine
      ])
    })
  }

  function muteFor(minutes) {
    var m = Number(minutes) || 0
    var untilEpoch = m > 0 ? (Math.floor(Date.now() / 1000) + Math.round(m * 60)) : 0
    if (m <= 0) _lastQuizEpoch = Math.floor(Date.now() / 1000)
    saveSettings({ mutedUntil: untilEpoch })
  }

  function openMainPanel(tabKey) {
    if (!mainPanelRef) return
    mainPanelRef.showTab(tabKey || "today")
  }

  function toggleMainPanel() {
    if (!mainPanelRef) return
    if (mainPanelRef.open && mainPanelRef.isOnCurrentWorkspace()) mainPanelRef.hideWindow()
    else mainPanelRef.showTab("")
  }

  function closeAll() {
    if (mainPanelRef) mainPanelRef.hideWindow()
  }

  // --- IPC İşleyicisi (`omarchy-shell lexis <komut>`) ---
  IpcHandler {
    target: "lexis"

    function panel(): string {
      svcRoot.toggleMainPanel()
      return "ok"
    }

    function tab(name: string): string {
      svcRoot.openMainPanel(String(name || "today").trim().toLowerCase())
      return "ok"
    }

    function toggle(): string {
      var mon = Hyprland.focusedMonitor
      var sname = mon && mon.name ? String(mon.name) : ""
      var bw = Bridge.barWidgetForScreen(sname)
      if (bw && typeof bw.togglePanel === "function") {
        bw.togglePanel()
        return "popout"
      }
      svcRoot.toggleMainPanel()
      return "panel"
    }

    function askNow(): string {
      svcRoot.askNow(0)
      return "ok"
    }

    function addSelection(): string {
      svcRoot.addSelection()
      return "ok"
    }

    function mute(minutes: string): string {
      svcRoot.muteFor(Number(minutes) || 0)
      return "ok"
    }

    function focusToast(): string {
      svcRoot.focusToastInput()
      return "ok"
    }

    function dismissToast(): string {
      if (svcRoot.activeQuestion) svcRoot.skipCurrent()
      else svcRoot.clearFeedback()
      return "ok"
    }

    function close(): string {
      svcRoot.closeAll()
      return "ok"
    }

    function reload(): string {
      svcRoot.refreshSnapshot(null)
      return "ok"
    }

    function status(): string {
      return JSON.stringify({
        answered: svcRoot.todayData ? (svcRoot.todayData.answered || 0) : 0,
        goal: svcRoot.todayData ? (svcRoot.todayData.goal || 50) : 50,
        totalWords: svcRoot.todayData ? (svcRoot.todayData.totalWords || 0) : 0,
        nextInSeconds: svcRoot.nextInSeconds,
        muted: svcRoot.isMuted,
        hasActiveQuestion: svcRoot.activeQuestion !== null,
        activeWord: svcRoot.activeQuestion ? svcRoot.activeQuestion.word : "",
        language: svcRoot.lang,
        aiProvider: svcRoot.settings ? svcRoot.settings.aiProvider : "off"
      })
    }
  }

  QuestionToastWindow {
    id: toastWin
    service: svcRoot
    fontFamily: Style.font.family
  }

  MainPanelWindow {
    id: mainPanelWin
    service: svcRoot
    fontFamily: Style.font.family
  }
}
