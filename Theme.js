.pragma library

// İki dilli metin yardımcısı (varsayılan English, seçilebilir Türkçe),
// CIE L* kontrast hesapları ve Omarchy canlı tema + Gruvbox Classic renk belirteçleri.

function t(lang, trText, enText) {
  return lang === "tr" ? trText : enText
}

function parseHexRgb(hexStr) {
  var s = String(hexStr || "").trim()
  if (s.charAt(0) === "#") s = s.slice(1)
  if (s.length === 3) {
    s = s.charAt(0) + s.charAt(0) + s.charAt(1) + s.charAt(1) + s.charAt(2) + s.charAt(2)
  }
  if (s.length < 6) return { r: 254, g: 128, b: 25 }
  var r = parseInt(s.substr(0, 2), 16)
  var g = parseInt(s.substr(2, 2), 16)
  var b = parseInt(s.substr(4, 2), 16)
  if (isNaN(r) || isNaN(g) || isNaN(b)) return { r: 254, g: 128, b: 25 }
  return { r: r, g: g, b: b }
}

function srgbToLinear(c255) {
  var c = c255 / 255.0
  return c <= 0.04045 ? (c / 12.92) : Math.pow((c + 0.055) / 1.055, 2.4)
}

function lightness(hexStr) {
  var rgb = parseHexRgb(hexStr)
  var y = 0.2126 * srgbToLinear(rgb.r) + 0.7152 * srgbToLinear(rgb.g) + 0.0722 * srgbToLinear(rgb.b)
  var l = y > 0.008856 ? (116.0 * Math.pow(y, 1.0 / 3.0) - 16.0) : (903.3 * y)
  return Math.max(0, Math.min(100, l))
}

function withAlpha(colorVal, a) {
  var alpha = Math.max(0, Math.min(1, Number(a)))
  if (typeof colorVal === "object" && colorVal !== null && colorVal.r !== undefined) {
    return Qt.rgba(colorVal.r, colorVal.g, colorVal.b, alpha)
  }
  var rgb = parseHexRgb(String(colorVal || "#ffffff"))
  return Qt.rgba(rgb.r / 255.0, rgb.g / 255.0, rgb.b / 255.0, alpha)
}

function mixColors(cA, cB, tRatio) {
  var a = (typeof cA === "object" && cA !== null && cA.r !== undefined)
    ? { r: cA.r, g: cA.g, b: cA.b }
    : (function() { var p = parseHexRgb(cA); return { r: p.r / 255, g: p.g / 255, b: p.b / 255 } })()
  var b = (typeof cB === "object" && cB !== null && cB.r !== undefined)
    ? { r: cB.r, g: cB.g, b: cB.b }
    : (function() { var p = parseHexRgb(cB); return { r: p.r / 255, g: p.g / 255, b: p.b / 255 } })()
  var k = Math.max(0, Math.min(1, Number(tRatio)))
  return Qt.rgba(a.r + (b.r - a.r) * k, a.g + (b.g - a.g) * k, a.b + (b.b - a.b) * k, 1.0)
}

function formatCountdown(seconds, lang) {
  var s = Math.max(0, Math.floor(Number(seconds) || 0))
  var m = Math.ceil(s / 60)
  if (s <= 59) return s + " " + t(lang, "sn", "s")
  return m + " " + t(lang, "dk", "min")
}

function greetingForNow(lang) {
  var h = (new Date()).getHours()
  if (h < 6) return t(lang, "İyi geceler", "Good night")
  if (h < 12) return t(lang, "Günaydın", "Good morning")
  if (h < 18) return t(lang, "İyi günler", "Good afternoon")
  return t(lang, "İyi akşamlar", "Good evening")
}

function boxLabel(boxVal, lang) {
  var b = Number(boxVal)
  if (isNaN(b) || b < 0) return t(lang, "Yeni", "New")
  if (b >= 4) return t(lang, "Oturan", "Settled") + " (" + b + "/5)"
  return t(lang, "Kutu ", "Box ") + b + "/5"
}

function qtypeLabel(qt, lang) {
  if (qt === "choice_word_meaning") return t(lang, "Kelime → Şıklı anlam", "Word → Multiple choice")
  if (qt === "choice_meaning_word") return t(lang, "Anlam → Şıklı kelime", "Meaning → Multiple choice")
  if (qt === "type_word_meaning") return t(lang, "Kelime → Yazılı anlam", "Word → Typed meaning")
  if (qt === "type_context") return t(lang, "Cümle içinde → Yazılı", "In context → Typed")
  return qt
}

function resolveTokens(themeMode, omarchyBg, omarchyFg, omarchyAccent, omarchyUrgent) {
  if (themeMode === "gruvbox") {
    return {
      win: "#282828",
      sidebar: "#1d2021",
      surface: "#32302f",
      surface2: "#3c3836",
      card: "#32302f",
      card2: "#3c3836",
      raised: "#504945",
      popup: Qt.rgba(29 / 255, 32 / 255, 33 / 255, 0.97),
      line: Qt.rgba(235 / 255, 219 / 255, 178 / 255, 0.11),
      lineStrong: Qt.rgba(235 / 255, 219 / 255, 178 / 255, 0.22),
      ink: "#ebdbb2",
      secondary: "#d5c4a1",
      muted: "#a89984",
      faint: "#665c54",
      primaryBg: "#fe8019",
      primaryInk: "#1d2021",
      accent: "#fe8019",
      ok: "#b8bb26",
      danger: "#fb4934",
      radius: 10,
      radiusSm: 7
    }
  }

  var bg = omarchyBg || Qt.rgba(16 / 255, 19 / 255, 21 / 255, 1)
  var fg = omarchyFg || Qt.rgba(218 / 255, 222 / 255, 226 / 255, 1)
  var acc = omarchyAccent || Qt.rgba(254 / 255, 128 / 255, 25 / 255, 1)
  var urg = omarchyUrgent || Qt.rgba(224 / 255, 100 / 255, 88 / 255, 1)

  var bgLum = 0.2126 * bg.r + 0.7152 * bg.g + 0.0722 * bg.b
  var isLight = bgLum > 0.5
  var sidebarCol = isLight ? mixColors(bg, fg, 0.035) : mixColors(bg, "#000000", 0.22)
  var cardCol = mixColors(bg, fg, isLight ? 0.045 : 0.055)
  var card2Col = mixColors(bg, fg, isLight ? 0.08 : 0.095)
  var raisedCol = mixColors(bg, fg, isLight ? 0.12 : 0.14)
  var accHex = "#" +
    ("0" + Math.round(acc.r * 255).toString(16)).slice(-2) +
    ("0" + Math.round(acc.g * 255).toString(16)).slice(-2) +
    ("0" + Math.round(acc.b * 255).toString(16)).slice(-2)
  var pInk = lightness(accHex) > 62 ? Qt.rgba(0.06, 0.07, 0.08, 1) : Qt.rgba(1, 1, 1, 1)

  return {
    win: Qt.rgba(bg.r, bg.g, bg.b, 1),
    sidebar: sidebarCol,
    surface: cardCol,
    surface2: card2Col,
    card: cardCol,
    card2: card2Col,
    raised: raisedCol,
    popup: Qt.rgba(bg.r, bg.g, bg.b, 0.97),
    line: withAlpha(fg, isLight ? 0.12 : 0.10),
    lineStrong: withAlpha(fg, isLight ? 0.22 : 0.20),
    ink: Qt.rgba(fg.r, fg.g, fg.b, 1),
    secondary: withAlpha(fg, 0.74),
    muted: withAlpha(fg, 0.50),
    faint: withAlpha(fg, 0.22),
    primaryBg: Qt.rgba(acc.r, acc.g, acc.b, 1),
    primaryInk: pInk,
    accent: Qt.rgba(acc.r, acc.g, acc.b, 1),
    ok: isLight ? "#2f8f4e" : "#8ec07c",
    danger: Qt.rgba(urg.r, urg.g, urg.b, 1),
    radius: 10,
    radiusSm: 7
  }
}
