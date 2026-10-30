import QtQuick
import Quickshell
import qs.Commons
import "../Theme.js" as Theme

// Ayarlar sekmesi: Arayüz dili (English / Türkçe), Tema (Omarchy Canlı / Gruvbox Classic),
// bar ilerleme ve soru ekranı seçimi, soru sıklığı (1–60 dk) ve günlük hedef (1–500),
// kullanıcı tanımlı dil çifti (targetLang / meaningLang), Hibrit Ücretsiz Sözlük +
// İsteğe Bağlı AI (Off, agy, claude, codex, Local/Custom /v1 ön ayarlar + model çekme + 0600 anahtar)
// ve yerel veri dışa aktarma / eski Kelime veritabanı taşıma.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  property string customKeyDraft: ""
  property string customFetchFeedback: ""

  readonly property bool isEditingText: targetLangInput.activeFocus
    || meaningLangInput.activeFocus
    || baseUrlInput.activeFocus
    || customModelInput.activeFocus
    || customKeyInput.activeFocus

  function releaseTextFocus() {
    if (!isEditingText) return false
    targetLangInput.focus = false
    meaningLangInput.focus = false
    baseUrlInput.focus = false
    customModelInput.focus = false
    customKeyInput.focus = false
    return true
  }

  function dismissOverlay() { return false }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var cfg: service && service.settings ? service.settings : ({})

  readonly property string uiLanguage: cfg.language === "tr" ? "tr" : "en"
  readonly property string themeMode: cfg.themeMode === "gruvbox" ? "gruvbox" : "omarchy"
  readonly property string toastScreen: String(cfg.toastScreen || "")
  readonly property int intervalMin: Math.max(1, Math.min(60, Number(cfg.intervalMin) || 5))
  readonly property int dailyGoal: Math.max(1, Math.min(500, Number(cfg.dailyGoal) || 50))
  readonly property string targetLang: String(cfg.targetLang || "English")
  readonly property string meaningLang: String(cfg.meaningLang || "Turkish")
  readonly property bool dictionaryEnabled: cfg.dictionaryEnabled !== false
  readonly property string aiProvider: String(cfg.aiProvider || "off")
  readonly property string customBaseUrl: String(cfg.customBaseUrl || "http://127.0.0.1:11434/v1")
  readonly property string customModel: String(cfg.customModel || "")

  function _providerMeta(pid) {
    var list = (service && service.providers) ? service.providers : []
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].id === pid) return list[i]
    }
    return null
  }

  function _commitLanguages() {
    if (!service) return
    var tl = String(targetLangInput.text || "").trim() || "English"
    var ml = String(meaningLangInput.text || "").trim() || "Turkish"
    if (tl !== targetLang || ml !== meaningLang) {
      service.saveSettings({ targetLang: tl, meaningLang: ml })
    }
  }

  function _commitCustomEndpoint() {
    if (!service) return
    var bu = String(baseUrlInput.text || "").trim()
    var cm = String(customModelInput.text || "").trim()
    service.saveSettings({ customBaseUrl: bu, customModel: cm })
  }

  Flickable {
    anchors.fill: parent
    contentWidth: width
    contentHeight: contentCol.implicitHeight + 68
    clip: true

    Column {
      id: contentCol
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: 34
      spacing: 22

      // Başlık
      Column {
        width: parent.width
        spacing: 4

        Text {
          text: Theme.t(root.lang, "Ayarlar", "Settings")
          font.family: root.fontFamily
          font.pixelSize: 22
          font.weight: Font.DemiBold
          color: root.tokens.ink || "#ebdbb2"
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: Theme.t(
            root.lang,
            "Görünüm, soru ritmi, öğrenilen dil çifti ve hibrit sözlük / isteğe bağlı AI bağlantısı.",
            "Appearance, quiz rhythm, learning language pair, and hybrid dictionary / optional AI."
          )
          font.family: root.fontFamily
          font.pixelSize: 13
          color: root.tokens.muted || "#a89984"
        }
      }

      // =====================================================================
      // BÖLÜM 1: GÖRÜNÜM VE BAR
      // =====================================================================
      Column {
        width: parent.width
        spacing: 12

        Text {
          text: Theme.t(root.lang, "GÖRÜNÜM VE ÜST BAR", "APPEARANCE & BAR")
          font.family: root.fontFamily
          font.pixelSize: 11
          font.weight: Font.DemiBold
          font.letterSpacing: 0.7
          color: root.tokens.muted || "#a89984"
        }

        // Arayüz dili + Tema yan yana
        Row {
          width: parent.width
          spacing: 24

          // Arayüz Dili
          Column {
            width: Math.floor((parent.width - 24) / 2)
            spacing: 6

            Text {
              text: Theme.t(root.lang, "Arayüz dili", "Interface language")
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.secondary || "#d5c4a1"
            }

            Flow {
              width: parent.width
              spacing: 6

              Repeater {
                model: [
                  { key: "en", label: "English" },
                  { key: "tr", label: "Türkçe" }
                ]
                delegate: Rectangle {
                  readonly property bool sel: root.uiLanguage === modelData.key
                  width: langChipTxt.implicitWidth + 22
                  height: 30
                  radius: 7
                  color: sel
                    ? (root.tokens.primaryBg || "#fe8019")
                    : (langChipArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f"))
                  border.width: sel ? 0 : 1
                  border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

                  Text {
                    id: langChipTxt
                    anchors.centerIn: parent
                    text: modelData.label
                    font.family: root.fontFamily
                    font.pixelSize: 12
                    font.weight: sel ? Font.DemiBold : Font.Normal
                    color: sel ? (root.tokens.primaryInk || "#1d2021") : (root.tokens.ink || "#ebdbb2")
                  }

                  MouseArea {
                    id: langChipArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) root.service.saveSettings({ language: modelData.key })
                    }
                  }
                }
              }
            }
          }

          // Tema
          Column {
            width: Math.floor((parent.width - 24) / 2)
            spacing: 6

            Text {
              text: Theme.t(root.lang, "Tema", "Theme")
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.secondary || "#d5c4a1"
            }

            Flow {
              width: parent.width
              spacing: 6

              Repeater {
                model: [
                  { key: "omarchy", label: Theme.t(root.lang, "Omarchy Canlı", "Omarchy Live") },
                  { key: "gruvbox", label: "Gruvbox Classic" }
                ]
                delegate: Rectangle {
                  readonly property bool sel: root.themeMode === modelData.key
                  width: themeChipTxt.implicitWidth + 20
                  height: 30
                  radius: 7
                  color: sel
                    ? (root.tokens.primaryBg || "#fe8019")
                    : (themeChipArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f"))
                  border.width: sel ? 0 : 1
                  border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

                  Text {
                    id: themeChipTxt
                    anchors.centerIn: parent
                    text: modelData.label
                    font.family: root.fontFamily
                    font.pixelSize: 12
                    font.weight: sel ? Font.DemiBold : Font.Normal
                    color: sel ? (root.tokens.primaryInk || "#1d2021") : (root.tokens.ink || "#ebdbb2")
                  }

                  MouseArea {
                    id: themeChipArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) root.service.saveSettings({ themeMode: modelData.key })
                    }
                  }
                }
              }
            }
          }
        }

        // Monitör seçici
        Row {
          width: parent.width
          spacing: 24

          // Bildirim kartı monitörü
          Column {
            width: parent.width
            spacing: 6

            Text {
              text: Theme.t(root.lang, "Soru kartı ekranı", "Question card monitor")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Flow {
              width: parent.width
              spacing: 6

              Rectangle {
                readonly property bool sel: root.toastScreen === ""
                width: focMonTxt.implicitWidth + 16
                height: 26
                radius: 6
                color: sel
                  ? (root.tokens.raised || "#504945")
                  : (focMonArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
                border.width: 1
                border.color: sel
                  ? (root.tokens.accent || "#fe8019")
                  : (root.tokens.line || Qt.rgba(1, 1, 1, 0.10))

                Text {
                  id: focMonTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Odaklı ekran", "Focused")
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: root.tokens.ink || "#ebdbb2"
                }

                MouseArea {
                  id: focMonArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service) root.service.saveSettings({ toastScreen: "" })
                  }
                }
              }

              Repeater {
                model: Quickshell.screens
                delegate: Rectangle {
                  readonly property string sname: modelData && modelData.name ? String(modelData.name) : ""
                  readonly property bool sel: root.toastScreen === sname && sname.length > 0
                  visible: sname.length > 0
                  width: scrMonTxt.implicitWidth + 16
                  height: 26
                  radius: 6
                  color: sel
                    ? (root.tokens.raised || "#504945")
                    : (scrMonArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
                  border.width: 1
                  border.color: sel
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.10))

                  Text {
                    id: scrMonTxt
                    anchors.centerIn: parent
                    text: parent.sname
                    font.family: "Monospace"
                    font.pixelSize: 11
                    color: root.tokens.ink || "#ebdbb2"
                  }

                  MouseArea {
                    id: scrMonArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) root.service.saveSettings({ toastScreen: parent.sname })
                    }
                  }
                }
              }
            }
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      // =====================================================================
      // BÖLÜM 2: SORU RİTMİ VE GÜNLÜK HEDEF
      // =====================================================================
      Column {
        width: parent.width
        spacing: 12

        Text {
          text: Theme.t(root.lang, "SORU RİTMİ", "QUIZ RHYTHM")
          font.family: root.fontFamily
          font.pixelSize: 11
          font.weight: Font.DemiBold
          font.letterSpacing: 0.7
          color: root.tokens.muted || "#a89984"
        }

        Row {
          width: parent.width
          spacing: 24

          // Sıklık (1..60 dk)
          Column {
            width: Math.floor((parent.width - 24) / 2)
            spacing: 6

            Text {
              text: Theme.t(root.lang, "Soru aralığı (dakika)", "Question interval (minutes)")
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.secondary || "#d5c4a1"
            }

            Flow {
              width: parent.width
              spacing: 6

              Rectangle {
                width: 28
                height: 28
                radius: 6
                color: intMinusArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f")
                Text { anchors.centerIn: parent; text: "−"; font.family: root.fontFamily; font.pixelSize: 14; color: root.tokens.ink || "#ebdbb2" }
                MouseArea {
                  id: intMinusArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service && root.intervalMin > 1) {
                      root.service.saveSettings({ intervalMin: root.intervalMin - 1 })
                    }
                  }
                }
              }

              Rectangle {
                width: 58
                height: 28
                radius: 6
                color: root.tokens.surface || "#32302f"
                border.width: 1
                border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

                Text {
                  anchors.centerIn: parent
                  text: root.intervalMin + " " + Theme.t(root.lang, "dk", "m")
                  font.family: "Monospace"
                  font.pixelSize: 12
                  font.weight: Font.DemiBold
                  color: root.tokens.ink || "#ebdbb2"
                }
              }

              Rectangle {
                width: 28
                height: 28
                radius: 6
                color: intPlusArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f")
                Text { anchors.centerIn: parent; text: "+"; font.family: root.fontFamily; font.pixelSize: 14; color: root.tokens.ink || "#ebdbb2" }
                MouseArea {
                  id: intPlusArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service && root.intervalMin < 60) {
                      root.service.saveSettings({ intervalMin: root.intervalMin + 1 })
                    }
                  }
                }
              }

              Repeater {
                model: [3, 5, 10, 15, 30]
                delegate: Rectangle {
                  readonly property bool sel: root.intervalMin === modelData
                  width: pIntTxt.implicitWidth + 12
                  height: 28
                  radius: 6
                  color: sel
                    ? (root.tokens.raised || "#504945")
                    : (pIntArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
                  border.width: 1
                  border.color: sel
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

                  Text {
                    id: pIntTxt
                    anchors.centerIn: parent
                    text: modelData + "m"
                    font.family: "Monospace"
                    font.pixelSize: 11
                    color: root.tokens.secondary || "#d5c4a1"
                  }

                  MouseArea {
                    id: pIntArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) root.service.saveSettings({ intervalMin: modelData })
                    }
                  }
                }
              }
            }
          }

          // Günlük hedef (1..500)
          Column {
            width: Math.floor((parent.width - 24) / 2)
            spacing: 6

            Text {
              text: Theme.t(root.lang, "Günlük soru hedefi", "Daily answer goal")
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.secondary || "#d5c4a1"
            }

            Flow {
              width: parent.width
              spacing: 6

              Rectangle {
                width: 28
                height: 28
                radius: 6
                color: goalMinusArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f")
                Text { anchors.centerIn: parent; text: "−"; font.family: root.fontFamily; font.pixelSize: 14; color: root.tokens.ink || "#ebdbb2" }
                MouseArea {
                  id: goalMinusArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service && root.dailyGoal > 5) {
                      root.service.saveSettings({ dailyGoal: Math.max(1, root.dailyGoal - 5) })
                    }
                  }
                }
              }

              Rectangle {
                width: 58
                height: 28
                radius: 6
                color: root.tokens.surface || "#32302f"
                border.width: 1
                border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

                Text {
                  anchors.centerIn: parent
                  text: String(root.dailyGoal)
                  font.family: "Monospace"
                  font.pixelSize: 12
                  font.weight: Font.DemiBold
                  color: root.tokens.ink || "#ebdbb2"
                }
              }

              Rectangle {
                width: 28
                height: 28
                radius: 6
                color: goalPlusArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f")
                Text { anchors.centerIn: parent; text: "+"; font.family: root.fontFamily; font.pixelSize: 14; color: root.tokens.ink || "#ebdbb2" }
                MouseArea {
                  id: goalPlusArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service && root.dailyGoal < 500) {
                      root.service.saveSettings({ dailyGoal: Math.min(500, root.dailyGoal + 5) })
                    }
                  }
                }
              }

              Repeater {
                model: [20, 50, 100, 150]
                delegate: Rectangle {
                  readonly property bool sel: root.dailyGoal === modelData
                  width: pGoalTxt.implicitWidth + 14
                  height: 28
                  radius: 6
                  color: sel
                    ? (root.tokens.raised || "#504945")
                    : (pGoalArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
                  border.width: 1
                  border.color: sel
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

                  Text {
                    id: pGoalTxt
                    anchors.centerIn: parent
                    text: String(modelData)
                    font.family: "Monospace"
                    font.pixelSize: 11
                    color: root.tokens.secondary || "#d5c4a1"
                  }

                  MouseArea {
                    id: pGoalArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) root.service.saveSettings({ dailyGoal: modelData })
                    }
                  }
                }
              }
            }
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      // =====================================================================
      // BÖLÜM 3: ÖĞRENİLEN DİL ÇİFTİ
      // =====================================================================
      Column {
        width: parent.width
        spacing: 10

        Text {
          text: Theme.t(root.lang, "ÖĞRENİLEN DİL ÇİFTİ", "LEARNING LANGUAGE PAIR")
          font.family: root.fontFamily
          font.pixelSize: 11
          font.weight: Font.DemiBold
          font.letterSpacing: 0.7
          color: root.tokens.muted || "#a89984"
        }

        Row {
          width: parent.width
          spacing: 16

          Column {
            width: Math.floor((parent.width - saveLangBtn.width - 32) / 2)
            spacing: 4

            Text {
              width: parent.width
              elide: Text.ElideRight
              text: Theme.t(root.lang, "Öğrendiğin dil (örn. English, German, Japanese)", "Target language (e.g. English, German, Japanese)")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Rectangle {
              width: parent.width
              height: 32
              radius: 7
              color: root.tokens.surface || "#32302f"
              border.width: 1
              border.color: targetLangInput.activeFocus
                ? (root.tokens.accent || "#fe8019")
                : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

              TextInput {
                id: targetLangInput
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                text: root.targetLang
                font.family: root.fontFamily
                font.pixelSize: 13
                color: root.tokens.ink || "#ebdbb2"
                onEditingFinished: root._commitLanguages()
                Keys.onReturnPressed: {
                  root._commitLanguages()
                  targetLangInput.focus = false
                }
              }
            }
          }

          Column {
            width: Math.floor((parent.width - saveLangBtn.width - 32) / 2)
            spacing: 4

            Text {
              width: parent.width
              elide: Text.ElideRight
              text: Theme.t(root.lang, "Anlam dili (örn. Turkish, English)", "Meaning language (e.g. Turkish, English)")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Rectangle {
              width: parent.width
              height: 32
              radius: 7
              color: root.tokens.surface || "#32302f"
              border.width: 1
              border.color: meaningLangInput.activeFocus
                ? (root.tokens.accent || "#fe8019")
                : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

              TextInput {
                id: meaningLangInput
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                text: root.meaningLang
                font.family: root.fontFamily
                font.pixelSize: 13
                color: root.tokens.ink || "#ebdbb2"
                onEditingFinished: root._commitLanguages()
                Keys.onReturnPressed: {
                  root._commitLanguages()
                  meaningLangInput.focus = false
                }
              }
            }
          }

          Rectangle {
            id: saveLangBtn
            anchors.bottom: parent.bottom
            width: Math.max(78, saveLangTxt.implicitWidth + 24)
            height: 32
            radius: 7
            color: saveLangArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: saveLangTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Kaydet", "Apply")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: saveLangArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root._commitLanguages()
            }
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      // =====================================================================
      // BÖLÜM 4: HİBRİT ÜCRETSİZ SÖZLÜK & İSTEĞE BAĞLI AI
      // =====================================================================
      Column {
        width: parent.width
        spacing: 12

        Text {
          text: Theme.t(root.lang, "HİBRİT SÖZLÜK VE İSTEĞE BAĞLI AI", "HYBRID DICTIONARY & OPTIONAL AI")
          font.family: root.fontFamily
          font.pixelSize: 11
          font.weight: Font.DemiBold
          font.letterSpacing: 0.7
          color: root.tokens.muted || "#a89984"
        }

        // Ücretsiz sözlük anahtarı
        Row {
          width: parent.width
          spacing: 12

          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 36
            height: 20
            radius: 10
            color: root.dictionaryEnabled
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.raised || "#504945")

            Rectangle {
              x: root.dictionaryEnabled ? 18 : 2
              anchors.verticalCenter: parent.verticalCenter
              width: 16
              height: 16
              radius: 8
              color: root.dictionaryEnabled
                ? (root.tokens.primaryInk || "#1d2021")
                : (root.tokens.muted || "#a89984")
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service) root.service.saveSettings({ dictionaryEnabled: !root.dictionaryEnabled })
              }
            }
          }

          Column {
            width: parent.width - 54
            spacing: 2

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: Theme.t(
                root.lang,
                "Birincil Ücretsiz Sözlük (Wiktionary + Tatoeba + MyMemory)",
                "Primary Free Dictionary (Wiktionary + Tatoeba + MyMemory)"
              )
              font.family: root.fontFamily
              font.pixelSize: 13
              font.weight: Font.Medium
              color: root.tokens.ink || "#ebdbb2"
            }

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: Theme.t(
                root.lang,
                "Giriş ve kota gerektirmez; yeni kelimelerin anlamını ve örnek cümlesini önce ücretsiz açık kaynak sözlüklerden çeker.",
                "Zero login, zero AI quota. Looks up meanings and example sentences from free open dictionaries first."
              )
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.muted || "#a89984"
            }
          }
        }

        // AI Yedek / Eş Anlamlı Hakemi Seçici
        Column {
          width: parent.width
          spacing: 6

          Text {
            text: Theme.t(
              root.lang,
              "İsteğe bağlı AI yedekleme ve eş anlamlı cevap kontrolü",
              "Optional AI fallback & synonym answer judge"
            )
            font.family: root.fontFamily
            font.pixelSize: 13
            color: root.tokens.secondary || "#d5c4a1"
          }

          Flow {
            width: parent.width
            spacing: 6

            Repeater {
              model: [
                { key: "off", label: Theme.t(root.lang, "Kapalı (Yalnız Sözlük)", "Off (Free Dictionary)") },
                { key: "agy", label: "Gemini (agy)" },
                { key: "claude", label: "Claude Code" },
                { key: "codex", label: "ChatGPT (Codex)" },
                { key: "custom", label: Theme.t(root.lang, "Yerel / Özel (/v1)", "Local / Custom (/v1)") }
              ]
              delegate: Rectangle {
                readonly property bool sel: root.aiProvider === modelData.key
                width: aiPillTxt.implicitWidth + 20
                height: 30
                radius: 7
                color: sel
                  ? (root.tokens.primaryBg || "#fe8019")
                  : (aiPillArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f"))
                border.width: sel ? 0 : 1
                border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

                Text {
                  id: aiPillTxt
                  anchors.centerIn: parent
                  text: modelData.label
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  font.weight: sel ? Font.DemiBold : Font.Normal
                  color: sel ? (root.tokens.primaryInk || "#1d2021") : (root.tokens.ink || "#ebdbb2")
                }

                MouseArea {
                  id: aiPillArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (!root.service) return
                    root.service.aiTestStatus = ""
                    root.service.saveSettings({ aiProvider: modelData.key })
                  }
                }
              }
            }
          }
        }

        // CLI Aboneliği Bağlantı Kartı (agy / claude / codex)
        Rectangle {
          visible: root.aiProvider === "agy" || root.aiProvider === "claude" || root.aiProvider === "codex"
          width: parent.width
          height: visible ? (cliInfoCol.implicitHeight + 24) : 0
          radius: 8
          color: root.tokens.surface || "#32302f"
          border.width: 1
          border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

          Column {
            id: cliInfoCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 12
            spacing: 8

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: {
                var meta = root._providerMeta(root.aiProvider)
                var inst = meta ? !!meta.installed : false
                var mod = meta && meta.model ? String(meta.model) : "low-tier"
                var statusStr = inst
                  ? Theme.t(root.lang, "CLI bulundu · en düşük kota modeli: ", "CLI detected · lowest-quota model: ") + mod
                  : Theme.t(root.lang, "CLI sistemde bulunamadı. Kurduktan sonra hesabını bağla.", "CLI binary not found on PATH. Install it first, then connect your account.")
                return statusStr
              }
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Row {
              spacing: 10

              Rectangle {
                width: cliLoginTxt.implicitWidth + 20
                height: 28
                radius: 6
                color: cliLoginArea.containsMouse
                  ? (root.tokens.raised || "#504945")
                  : (root.tokens.surface2 || "#3c3836")
                border.width: 1
                border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

                Text {
                  id: cliLoginTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Terminalde hesabı bağla…", "Connect account in terminal…")
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                }

                MouseArea {
                  id: cliLoginArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service) root.service.openAiLogin(root.aiProvider)
                  }
                }
              }
            }
          }
        }

        // Yerel / Özel OpenAI-Uyumlu (/v1) Paneli
        Rectangle {
          visible: root.aiProvider === "custom"
          width: parent.width
          height: visible ? (customBoxCol.implicitHeight + 28) : 0
          radius: 8
          color: root.tokens.surface || "#32302f"
          border.width: 1
          border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

          Column {
            id: customBoxCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 14
            spacing: 10

            // Tek tık ön ayarlar
            Flow {
              width: parent.width
              spacing: 6

              Text {
                topPadding: 4
                text: Theme.t(root.lang, "Ön ayar:", "Presets:")
                font.family: root.fontFamily
                font.pixelSize: 11
                color: root.tokens.muted || "#a89984"
              }

              Repeater {
                model: [
                  { label: "Ollama (:11434)", url: "http://127.0.0.1:11434/v1" },
                  { label: "LM Studio (:1234)", url: "http://127.0.0.1:1234/v1" },
                  { label: "llama.cpp (:8080)", url: "http://127.0.0.1:8080/v1" },
                  { label: "OpenRouter", url: "https://openrouter.ai/api/v1" }
                ]
                delegate: Rectangle {
                  readonly property bool sel: root.customBaseUrl === modelData.url
                  width: presetUrlTxt.implicitWidth + 14
                  height: 24
                  radius: 5
                  color: sel
                    ? (root.tokens.raised || "#504945")
                    : (presetUrlArea.containsMouse ? (root.tokens.surface2 || "#3c3836") : "transparent")
                  border.width: 1
                  border.color: sel
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

                  Text {
                    id: presetUrlTxt
                    anchors.centerIn: parent
                    text: modelData.label
                    font.family: root.fontFamily
                    font.pixelSize: 11
                    color: root.tokens.ink || "#ebdbb2"
                  }

                  MouseArea {
                    id: presetUrlArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      baseUrlInput.text = modelData.url
                      if (root.service) {
                        root.service.saveSettings({ customBaseUrl: modelData.url })
                      }
                    }
                  }
                }
              }
            }

            // Base URL + Modelleri Çek
            Row {
              width: parent.width
              spacing: 8

              Rectangle {
                width: parent.width - fetchModBtn.width - 8
                height: 30
                radius: 6
                color: root.tokens.surface2 || "#3c3836"
                border.width: 1
                border.color: baseUrlInput.activeFocus
                  ? (root.tokens.accent || "#fe8019")
                  : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

                TextInput {
                  id: baseUrlInput
                  anchors.fill: parent
                  anchors.leftMargin: 8
                  anchors.rightMargin: 8
                  verticalAlignment: TextInput.AlignVCenter
                  clip: true
                  text: root.customBaseUrl
                  font.family: "Monospace"
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                  onEditingFinished: root._commitCustomEndpoint()
                }
              }

              Rectangle {
                id: fetchModBtn
                width: Math.max(116, fetchModTxt.implicitWidth + 22)
                height: 30
                radius: 6
                color: fetchModArea.containsMouse
                  ? (root.tokens.raised || "#504945")
                  : (root.tokens.surface2 || "#3c3836")
                border.width: 1
                border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

                Text {
                  id: fetchModTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Modelleri çek", "Fetch models")
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                }

                MouseArea {
                  id: fetchModArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (!root.service) return
                    root._commitCustomEndpoint()
                    root.customFetchFeedback = Theme.t(root.lang, "Sorgulanıyor…", "Fetching…")
                    root.service.fetchCustomModels(baseUrlInput.text, function(res) {
                      if (res && res.ok && res.models && res.models.length > 0) {
                        root.customFetchFeedback = res.models.length + " " + Theme.t(root.lang, "model bulundu", "models found")
                      } else {
                        root.customFetchFeedback = Theme.t(root.lang, "Model listesi alınamadı", "Could not list models")
                      }
                    })
                  }
                }
              }
            }

            // Model adı girişi + çekilen modellerden tek tık seçim
            Row {
              width: parent.width
              spacing: 8

              Rectangle {
                width: parent.width - saveModBtn.width - 8
                height: 30
                radius: 6
                color: root.tokens.surface2 || "#3c3836"
                border.width: 1
                border.color: customModelInput.activeFocus
                  ? (root.tokens.accent || "#fe8019")
                  : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

                Text {
                  visible: customModelInput.text.length === 0
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.leftMargin: 8
                  anchors.rightMargin: 8
                  anchors.verticalCenter: parent.verticalCenter
                  elide: Text.ElideRight
                  text: Theme.t(root.lang, "Model adı (örn. qwen2.5:7b, llama3.2:3b)", "Model ID (e.g. qwen2.5:7b, llama3.2:3b)")
                  font.family: "Monospace"
                  font.pixelSize: 11
                  color: root.tokens.muted || "#a89984"
                }

                TextInput {
                  id: customModelInput
                  anchors.fill: parent
                  anchors.leftMargin: 8
                  anchors.rightMargin: 8
                  verticalAlignment: TextInput.AlignVCenter
                  clip: true
                  text: root.customModel
                  font.family: "Monospace"
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                  onEditingFinished: root._commitCustomEndpoint()
                  Keys.onReturnPressed: {
                    root._commitCustomEndpoint()
                    customModelInput.focus = false
                  }
                }
              }

              Rectangle {
                id: saveModBtn
                width: Math.max(82, saveModTxt.implicitWidth + 22)
                height: 30
                radius: 6
                color: saveModArea.containsMouse
                  ? (root.tokens.raised || "#504945")
                  : (root.tokens.surface2 || "#3c3836")
                border.width: 1
                border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

                Text {
                  id: saveModTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Kaydet", "Save")
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                }

                MouseArea {
                  id: saveModArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root._commitCustomEndpoint()
                }
              }
            }

            Text {
              visible: root.customFetchFeedback.length > 0
              text: root.customFetchFeedback
              font.family: root.fontFamily
              font.pixelSize: 11
              color: root.tokens.muted || "#a89984"
            }

            Flow {
              visible: !!(root.service && root.service.customModels && root.service.customModels.length > 0)
              width: parent.width
              spacing: 5

              Repeater {
                model: (root.service && root.service.customModels)
                  ? root.service.customModels.slice(0, 14)
                  : []
                delegate: Rectangle {
                  readonly property bool sel: root.customModel === String(modelData)
                  width: Math.min(240, mChipTxt.implicitWidth + 14)
                  height: 22
                  radius: 5
                  color: sel
                    ? (root.tokens.raised || "#504945")
                    : (mChipArea.containsMouse ? (root.tokens.surface2 || "#3c3836") : "transparent")
                  border.width: 1
                  border.color: sel
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.10))

                  Text {
                    id: mChipTxt
                    anchors.centerIn: parent
                    width: Math.min(226, implicitWidth)
                    elide: Text.ElideRight
                    text: String(modelData)
                    font.family: "Monospace"
                    font.pixelSize: 10
                    color: root.tokens.ink || "#ebdbb2"
                  }

                  MouseArea {
                    id: mChipArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      customModelInput.text = String(modelData)
                      if (root.service) root.service.saveSettings({ customModel: String(modelData) })
                    }
                  }
                }
              }
            }

            // İsteğe bağlı API anahtarı (~/.local/state/lexis/api_key, 0600)
            Row {
              width: parent.width
              spacing: 8

              Rectangle {
                width: parent.width - saveKeyBtn.width - (clrKeyBtn.visible ? (clrKeyBtn.width + 16) : 8)
                height: 30
                radius: 6
                color: root.tokens.surface2 || "#3c3836"
                border.width: 1
                border.color: customKeyInput.activeFocus
                  ? (root.tokens.accent || "#fe8019")
                  : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

                Text {
                  visible: customKeyInput.text.length === 0
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.leftMargin: 8
                  anchors.rightMargin: 8
                  anchors.verticalCenter: parent.verticalCenter
                  elide: Text.ElideRight
                  text: (root.service && root.service.hasCustomApiKey)
                    ? Theme.t(root.lang, "Kayıtlı anahtar var (0600) — değiştirmek için yaz", "API key saved (0600) — type to replace")
                    : Theme.t(root.lang, "İsteğe bağlı API anahtarı (Ollama/LM Studio için boş bırak)", "Optional API key (leave empty for local Ollama/LM Studio)")
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: root.tokens.muted || "#a89984"
                }

                TextInput {
                  id: customKeyInput
                  anchors.fill: parent
                  anchors.leftMargin: 8
                  anchors.rightMargin: 8
                  verticalAlignment: TextInput.AlignVCenter
                  echoMode: TextInput.Password
                  clip: true
                  text: root.customKeyDraft
                  onTextChanged: root.customKeyDraft = text
                  font.family: "Monospace"
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                }
              }

              Rectangle {
                id: saveKeyBtn
                width: Math.max(90, saveKeyTxt.implicitWidth + 20)
                height: 30
                radius: 6
                color: saveKeyArea.containsMouse
                  ? (root.tokens.raised || "#504945")
                  : (root.tokens.surface2 || "#3c3836")
                border.width: 1
                border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

                Text {
                  id: saveKeyTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Anahtar kaydet", "Save key")
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: root.tokens.ink || "#ebdbb2"
                }

                MouseArea {
                  id: saveKeyArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (!root.service || !root.customKeyDraft.trim()) return
                    root.service.saveCustomApiKey(root.customKeyDraft.trim(), function() {
                      root.customKeyDraft = ""
                    })
                  }
                }
              }

              Rectangle {
                id: clrKeyBtn
                visible: !!(root.service && root.service.hasCustomApiKey)
                width: Math.max(76, clrKeyTxt.implicitWidth + 20)
                height: 30
                radius: 6
                color: clrKeyArea.containsMouse
                  ? (root.tokens.raised || "#504945")
                  : "transparent"
                border.width: 1
                border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

                Text {
                  id: clrKeyTxt
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Temizle", "Clear")
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: root.tokens.danger || "#fb4934"
                }

                MouseArea {
                  id: clrKeyArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service) root.service.clearCustomApiKey(null)
                  }
                }
              }
            }
          }
        }

        // Bağlantıyı sına düğmesi + sonuç
        Flow {
          width: parent.width
          spacing: 12

          Rectangle {
            width: testConnTxt.implicitWidth + 22
            height: 30
            radius: 7
            color: testConnArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

            Text {
              id: testConnTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Bağlantıyı sına", "Test connection")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: testConnArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (!root.service) return
                if (root.aiProvider === "custom") root._commitCustomEndpoint()
                root.service.testAiConnection()
              }
            }
          }

          Text {
            visible: !!(root.service && root.service.aiTestStatus)
            topPadding: 6
            width: Math.min(implicitWidth, parent.width)
            wrapMode: Text.WordWrap
            text: root.service ? String(root.service.aiTestStatus || "") : ""
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.secondary || "#d5c4a1"
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      // =====================================================================
      // BÖLÜM 5: YEREL VERİ VE YEDEK
      // =====================================================================
      Column {
        width: parent.width
        spacing: 10

        Text {
          text: Theme.t(root.lang, "YEREL VERİ VE TAŞIMA", "LOCAL DATA & MIGRATION")
          font.family: root.fontFamily
          font.pixelSize: 11
          font.weight: Font.DemiBold
          font.letterSpacing: 0.7
          color: root.tokens.muted || "#a89984"
        }

        Text {
          width: parent.width
          elide: Text.ElideMiddle
          text: "SQLite: " + (root.service ? root.service.dbPath : "~/.local/share/lexis/lexis.sqlite")
          font.family: "Monospace"
          font.pixelSize: 11
          color: root.tokens.muted || "#a89984"
        }

        Flow {
          width: parent.width
          spacing: 10

          Rectangle {
            width: expCsvTxt.implicitWidth + 22
            height: 32
            radius: 7
            color: expCsvArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: expCsvTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "CSV olarak dışa aktar…", "Export CSV…")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: expCsvArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service) root.service.exportCsvDialog()
              }
            }
          }

          Rectangle {
            visible: !!(root.service && root.service.legacyAvailable)
            width: legImpTxt.implicitWidth + 22
            height: 32
            radius: 7
            color: legImpArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.accent || "#fe8019"

            Text {
              id: legImpTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Eski Kelime veritabanını aktar", "Import from legacy Kelime")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: legImpArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service) root.service.importLegacyDb()
              }
            }
          }

          Text {
            visible: !!(root.service && root.service.statusNotice)
            topPadding: 7
            width: Math.min(implicitWidth, parent.width)
            wrapMode: Text.WordWrap
            text: root.service ? String(root.service.statusNotice || "") : ""
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.accent || "#fe8019"
          }
        }
      }
    }
  }
}
