import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import "../Theme.js" as Theme
import "../components"

// Sağ üst köşede bildirim gibi beliren, kendiliğinden kapanmayan ve odak çalmayan soru kartı.
// Kart dışındaki tüm ekran pikselleri Region maskesi sayesinde %100 tıklama geçirgendir.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  property bool inputActive: false
  property var capturedScreen: null

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var question: service ? service.activeQuestion : null
  readonly property var feedback: (!question && service) ? service.feedbackToast : null
  readonly property bool active: (question !== null || feedback !== null)
    && !(service && service.nativeDialogOpen)

  readonly property bool isIntro: !!(question && question.qtype === "intro")
  readonly property bool isChoice: !!(question && (question.qtype === "choice_word_meaning" || question.qtype === "choice_meaning_word"))
  readonly property bool isTyped: !!(question && (question.qtype === "type_word_meaning" || question.qtype === "type_context"))

  readonly property string barPosition: service && service.shell && service.shell.barConfig
    ? String(service.shell.barConfig.position || "top")
    : "top"
  readonly property bool barVertical: barPosition === "left" || barPosition === "right"
  readonly property int defaultBarSize: barVertical ? Style.bar.sizeVertical : Style.bar.sizeHorizontal
  readonly property int liveBarSize: service && service.shell && service.shell.bar && !service.shell.bar.barHidden
    ? Math.max(0, service.shell.bar.barSize)
    : defaultBarSize
  readonly property int topClearance: barPosition === "top"
    ? (liveBarSize + Style.gapsOut)
    : Math.max(12, Style.gapsOut)
  readonly property int rightClearance: barPosition === "right"
    ? (liveBarSize + Style.gapsOut)
    : Math.max(12, Style.gapsOut)

  function _resolveScreen() {
    var screens = Quickshell.screens
    if (!screens || screens.length === 0) return null
    var pinned = service && service.settings && service.settings.toastScreen
      ? String(service.settings.toastScreen)
      : ""
    if (pinned) {
      for (var i = 0; i < screens.length; i++) {
        if (String(screens[i].name) === pinned) return screens[i]
      }
    }
    var mon = Hyprland.focusedMonitor
    if (mon) {
      for (var j = 0; j < screens.length; j++) {
        if (String(screens[j].name) === String(mon.name)) return screens[j]
      }
    }
    return screens[0]
  }

  onQuestionChanged: {
    inputActive = false
    answerInput.text = ""
    if (question !== null) {
      var s = _resolveScreen()
      if (s) capturedScreen = s
    }
  }

  onFeedbackChanged: {
    inputActive = false
    if (feedback !== null) {
      if (!capturedScreen) capturedScreen = _resolveScreen()
      feedbackTimer.restart()
    } else {
      feedbackTimer.stop()
    }
  }

  function focusInput() {
    if (!question) return
    inputActive = true
    Qt.callLater(function() {
      if (root.isTyped) answerInput.forceActiveFocus()
      else toastKeyScope.forceActiveFocus()
    })
  }

  Timer {
    id: feedbackTimer
    interval: 6000
    repeat: false
    onTriggered: {
      if (root.service) root.service.clearFeedback()
    }
  }

  PanelWindow {
    id: win
    screen: root.capturedScreen || root._resolveScreen()
    visible: root.active
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore

    WlrLayershell.namespace: "lexis-toast"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: (win.visible && root.inputActive && root.question !== null)
      ? WlrKeyboardFocus.OnDemand
      : WlrKeyboardFocus.None

    anchors {
      top: true
      bottom: true
      left: true
      right: true
    }

    mask: Region {
      item: toastCard
    }

    Rectangle {
      id: toastCard
      width: 356
      height: cardCol.implicitHeight + 28
      anchors.top: parent.top
      anchors.right: parent.right
      anchors.topMargin: root.topClearance
      anchors.rightMargin: root.rightClearance
      radius: Math.max(8, Style.cornerRadius)
      color: root.tokens.popup || "#1d2021"
      border.width: 1
      border.color: root.inputActive
        ? (root.tokens.accent || "#fe8019")
        : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.18))

      FocusScope {
        id: toastKeyScope
        anchors.fill: parent
        focus: root.inputActive

        Keys.onPressed: function(event) {
          var k = event.key
          if (k === Qt.Key_Escape) {
            event.accepted = true
            if (root.inputActive) {
              root.inputActive = false
            } else if (root.service && root.question) {
              root.service.skipCurrent()
            }
            return
          }
          if (root.isIntro && (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space)) {
            event.accepted = true
            if (root.service) root.service.ackIntro()
            return
          }
          if (root.isChoice && root.service && !(service && service.judging)) {
            var idx = -1
            if (k === Qt.Key_1) idx = 0
            else if (k === Qt.Key_2) idx = 1
            else if (k === Qt.Key_3) idx = 2
            else if (k === Qt.Key_4) idx = 3
            if (idx >= 0 && root.question && root.question.choices && idx < root.question.choices.length) {
              event.accepted = true
              root.inputActive = false
              root.service.submitChoice(idx)
            }
          }
        }

        Column {
          id: cardCol
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: 14
          spacing: 10

          // --- ÜST ŞERİT: Marka + Etiket + Bir daha gösterme + ✕ ---
          Item {
            width: parent.width
            height: 20

            Row {
              anchors.left: parent.left
              anchors.right: toastRightBtns.left
              anchors.rightMargin: 8
              anchors.verticalCenter: parent.verticalCenter
              spacing: 7

              LexisGlyph {
                id: toastGlyph
                anchors.verticalCenter: parent.verticalCenter
                pixelSize: 13
                inkColor: root.tokens.ink || "#ebdbb2"
                dotColor: root.tokens.accent || "#fe8019"
                fontFamily: root.fontFamily
              }

              Text {
                width: Math.max(40, parent.width - toastGlyph.width - 7)
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
                text: {
                  if (root.question) return String(root.question.prompt || "")
                  if (root.feedback) {
                    if (root.feedback.infoOnly) return String(root.feedback.badge || "Lexis")
                    return root.feedback.correct
                      ? Theme.t(root.lang, "✓ Doğru", "✓ Correct")
                      : Theme.t(root.lang, "✗ Doğru cevap", "✗ Right answer")
                  }
                  return ""
                }
                font.family: root.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                color: {
                  if (root.feedback && !root.feedback.infoOnly) {
                    return root.feedback.correct
                      ? (root.tokens.ok || "#b8bb26")
                      : (root.tokens.danger || "#fb4934")
                  }
                  return root.tokens.muted || "#a89984"
                }
              }
            }

            Row {
              id: toastRightBtns
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: 6

              Rectangle {
                visible: root.question !== null
                height: 20
                width: hideLbl.implicitWidth + 10
                radius: 5
                color: hideArea.containsMouse
                  ? Theme.withAlpha(root.tokens.ink || "#ffffff", 0.10)
                  : "transparent"

                Text {
                  id: hideLbl
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Bir daha gösterme", "Don't show again")
                  font.family: root.fontFamily
                  font.pixelSize: 10
                  color: hideArea.containsMouse
                    ? (root.tokens.ink || "#ebdbb2")
                    : (root.tokens.muted || "#a89984")
                }

                MouseArea {
                  id: hideArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.inputActive = false
                    if (root.service) root.service.hideCurrentWord()
                  }
                }
              }

              Rectangle {
                width: 20
                height: 20
                radius: 5
                color: closeArea.containsMouse
                  ? Theme.withAlpha(root.tokens.ink || "#ffffff", 0.12)
                  : "transparent"

                Text {
                  anchors.centerIn: parent
                  text: "✕"
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: closeArea.containsMouse
                    ? (root.tokens.ink || "#ebdbb2")
                    : (root.tokens.muted || "#a89984")
                }

                MouseArea {
                  id: closeArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.inputActive = false
                    if (!root.service) return
                    if (root.question) root.service.skipCurrent()
                    else root.service.clearFeedback()
                  }
                }
              }
            }
          }

          // --- AKTİF SORU VEYA TANIŞMA KARTI ---
          Column {
            visible: root.question !== null
            width: parent.width
            spacing: 10

            Text {
              width: parent.width
              text: root.question ? String(root.question.title || "") : ""
              wrapMode: Text.WordWrap
              font.family: root.fontFamily
              font.pixelSize: 16
              font.weight: Font.DemiBold
              color: root.tokens.ink || "#ebdbb2"
            }

            // Örnek cümle / çeviri (tanışma ve type_context için)
            Rectangle {
              visible: !!(root.question && root.question.bodyHtml && String(root.question.bodyHtml).length > 0)
              width: parent.width
              height: visible ? (bodyTxt.implicitHeight + 14) : 0
              radius: 6
              color: Theme.withAlpha(root.tokens.ink || "#ffffff", 0.05)

              Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 2
                radius: 1
                color: root.tokens.accent || "#fe8019"
              }

              Text {
                id: bodyTxt
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                text: root.question ? String(root.question.bodyHtml || "") : ""
                textFormat: Text.RichText
                wrapMode: Text.WordWrap
                font.family: root.fontFamily
                font.pixelSize: 12
                color: root.tokens.secondary || "#d5c4a1"
              }
            }

            // 1) TANIŞMA DÜĞMESİ
            Rectangle {
              visible: root.isIntro
              width: parent.width
              height: 32
              radius: 7
              color: introBtnArea.containsMouse
                ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
                : (root.tokens.primaryBg || "#fe8019")

              Text {
                anchors.centerIn: parent
                text: Theme.t(root.lang, "Tamam", "Got it")
                font.family: root.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                color: root.tokens.primaryInk || "#1d2021"
              }

              MouseArea {
                id: introBtnArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  root.inputActive = false
                  if (root.service) root.service.ackIntro()
                }
              }
            }

            // 2) 4 ŞIKLI DÜĞMELER
            Column {
              visible: root.isChoice
              width: parent.width
              spacing: 5

              Repeater {
                model: (root.isChoice && root.question && root.question.choices) ? root.question.choices : []
                delegate: Rectangle {
                  width: cardCol.width
                  height: 30
                  radius: 6
                  color: choiceArea.containsMouse
                    ? (root.tokens.raised || "#504945")
                    : (root.tokens.surface2 || "#3c3836")
                  border.width: 1
                  border.color: choiceArea.containsMouse
                    ? (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.22))
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

                  Row {
                    anchors.fill: parent
                    anchors.leftMargin: 9
                    anchors.rightMargin: 9
                    spacing: 8

                    Text {
                      width: 14
                      anchors.verticalCenter: parent.verticalCenter
                      text: String(index + 1)
                      font.family: "Monospace"
                      font.pixelSize: 11
                      color: root.tokens.muted || "#a89984"
                    }

                    Text {
                      width: parent.width - 26
                      anchors.verticalCenter: parent.verticalCenter
                      text: String(modelData || "")
                      elide: Text.ElideRight
                      font.family: root.fontFamily
                      font.pixelSize: 12
                      color: root.tokens.ink || "#ebdbb2"
                    }
                  }

                  MouseArea {
                    id: choiceArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.inputActive = false
                      if (root.service) root.service.submitChoice(index)
                    }
                  }
                }
              }
            }

            // 3) YAZILI YANIT KUTUSU (yalnız tıklanınca veya focusToast IPC ile odak alır)
            Row {
              visible: root.isTyped
              width: parent.width
              spacing: 6

              Rectangle {
                width: parent.width - 74
                height: 32
                radius: 6
                color: root.tokens.surface2 || "#3c3836"
                border.width: 1
                border.color: root.inputActive
                  ? (root.tokens.accent || "#fe8019")
                  : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16))

                Text {
                  visible: answerInput.text.length === 0 && !root.inputActive
                  anchors.left: parent.left
                  anchors.leftMargin: 9
                  anchors.verticalCenter: parent.verticalCenter
                  text: Theme.t(root.lang, "Yanıt yazmak için tıkla…", "Click to type answer…")
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  color: root.tokens.muted || "#a89984"
                }

                TextInput {
                  id: answerInput
                  anchors.fill: parent
                  anchors.leftMargin: 9
                  anchors.rightMargin: 9
                  verticalAlignment: TextInput.AlignVCenter
                  clip: true
                  enabled: !(root.service && root.service.judging)
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  color: root.tokens.ink || "#ebdbb2"
                  selectionColor: root.tokens.accent || "#fe8019"
                  selectedTextColor: root.tokens.primaryInk || "#1d2021"

                  Keys.onReturnPressed: {
                    if (root.service && !root.service.judging) {
                      var val = answerInput.text
                      root.inputActive = false
                      root.service.submitTyped(val)
                    }
                  }
                  Keys.onEnterPressed: {
                    if (root.service && !root.service.judging) {
                      var val2 = answerInput.text
                      root.inputActive = false
                      root.service.submitTyped(val2)
                    }
                  }
                  Keys.onEscapePressed: {
                    root.inputActive = false
                  }
                }

                MouseArea {
                  anchors.fill: parent
                  visible: !root.inputActive
                  cursorShape: Qt.IBeamCursor
                  onClicked: root.focusInput()
                }
              }

              Rectangle {
                width: 68
                height: 32
                radius: 6
                color: sendArea.containsMouse
                  ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
                  : (root.tokens.primaryBg || "#fe8019")

                Text {
                  anchors.centerIn: parent
                  text: (root.service && root.service.judging)
                    ? "…"
                    : Theme.t(root.lang, "Gönder", "Reply")
                  font.family: root.fontFamily
                  font.pixelSize: 12
                  font.weight: Font.DemiBold
                  color: root.tokens.primaryInk || "#1d2021"
                }

                MouseArea {
                  id: sendArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service && !root.service.judging) {
                      var val = answerInput.text
                      root.inputActive = false
                      root.service.submitTyped(val)
                    }
                  }
                }
              }
            }
          }

          // --- 6 SANİYELİK GERİ BİLDİRİM / BİLGİ KARTI ---
          Column {
            visible: root.question === null && root.feedback !== null
            width: parent.width
            spacing: 7

            Text {
              width: parent.width
              text: {
                if (!root.feedback) return ""
                if (root.feedback.infoOnly) return String(root.feedback.headline || "")
                return String(root.feedback.word || "") + " — " + String(root.feedback.rightAnswer || "")
              }
              wrapMode: Text.WordWrap
              font.family: root.fontFamily
              font.pixelSize: 14
              font.weight: Font.DemiBold
              color: root.tokens.ink || "#ebdbb2"
            }

            Text {
              visible: !!(root.feedback && root.feedback.exampleHtml && String(root.feedback.exampleHtml).length > 0)
              width: parent.width
              text: root.feedback ? String(root.feedback.exampleHtml || "") : ""
              textFormat: Text.RichText
              wrapMode: Text.WordWrap
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }
          }
        }
      }
    }
  }
}
