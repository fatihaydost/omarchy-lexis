import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "../Theme.js" as Theme

// Üst bardaki "l." düğmesine sol tıklandığında açılan hızlı menü:
// Günlük ilerleme çubuğu, sıradaki soru sayacı, hızlı kelime ekleme satırı,
// Şimdi sor / 1 saat sustur düğmeleri ve ana pencere kısayolları.
Item {
  id: root

  property QtObject bar: null
  property var anchorItem: null
  property var hostWidget: null
  property var service: null
  property bool popoutSwitchClosing: false
  property string quickNotice: ""
  property int kbIndex: 0
  property bool kbActive: false

  readonly property bool opened: panelController.open
  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service
    ? service.tokens
    : Theme.resolveTokens("omarchy", Commons.Color.background, Commons.Color.foreground, Commons.Color.accent, Commons.Color.urgent)

  readonly property int answered: service && service.todayData ? (Number(service.todayData.answered) || 0) : 0
  readonly property int goal: service && service.todayData ? Math.max(1, Number(service.todayData.goal) || 50) : 50
  readonly property real goalRatio: Math.max(0.0, Math.min(1.0, answered / goal))

  onOpenedChanged: {
    if (!opened) {
      quickInput.text = ""
      quickInput.focus = false
      quickNotice = ""
      kbActive = false
    } else {
      kbIndex = 0
      kbActive = false
    }
  }

  function open() { panelController.show() }
  function close() { panelController.hide() }
  function toggle() { opened ? close() : open() }
  function closeForPopoutSwitch() {
    popoutSwitchClosing = true
    close()
    Qt.callLater(function() { popoutSwitchClosing = false })
  }

  function submitQuickWord() {
    var txt = String(quickInput.text || "").trim()
    if (!txt || !service) return
    quickInput.text = ""
    service.addWordQuick(txt, function(res) {
      if (res && res.duplicate) {
        root.quickNotice = Theme.t(root.lang, "Zaten listede", "Already in deck")
      } else {
        root.quickNotice = Theme.t(root.lang, "✓ Eklendi", "✓ Added")
      }
      noticeClearTimer.restart()
    })
  }

  function triggerNavIndex(idx) {
    if (!service) return
    if (idx === 0) {
      quickInput.forceActiveFocus()
    } else if (idx === 1) {
      close()
      service.askNow(0)
    } else if (idx === 2) {
      service.muteFor(service.isMuted ? 0 : 60)
    } else if (idx === 3) {
      close()
      service.openMainPanel("today")
    } else if (idx === 4) {
      close()
      service.openMainPanel("words")
    } else if (idx === 5) {
      close()
      service.openMainPanel("translate")
    } else if (idx === 6) {
      close()
      service.openMainPanel("settings")
    }
  }

  Timer {
    id: noticeClearTimer
    interval: 3000
    repeat: false
    onTriggered: root.quickNotice = ""
  }

  PanelController {
    id: panelController
  }

  KeyboardPanel {
    id: popup
    anchorItem: root.anchorItem
    bar: root.bar
    owner: root.hostWidget || root
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: popup.fittedContentWidth(Style.space(304))
    contentHeight: popup.fittedContentHeight(menuCol.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: {
        if (quickInput.activeFocus) {
          quickInput.focus = false
          keyCatcher.forceActiveFocus()
        } else {
          root.close()
        }
      }

      Keys.onPressed: function(event) {
        var k = event.key
        var mods = event.modifiers
        if ((mods & Qt.ControlModifier) && (k === Qt.Key_W || k === Qt.Key_Q)) {
          event.accepted = true
          root.close()
          return
        }
        if (quickInput.activeFocus) return
        if (k === Qt.Key_Down || k === Qt.Key_Tab) {
          event.accepted = true
          root.kbIndex = root.kbActive ? ((root.kbIndex + 1) % 7) : 0
          root.kbActive = true
          return
        }
        if (k === Qt.Key_Up || k === Qt.Key_Backtab) {
          event.accepted = true
          root.kbIndex = root.kbActive ? ((root.kbIndex + 6) % 7) : 0
          root.kbActive = true
          return
        }
        if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
          event.accepted = true
          root.kbActive = true
          root.triggerNavIndex(root.kbIndex)
        }
      }
    }

    Column {
      id: menuCol
      width: parent.width
      spacing: 10

      // --- Başlık + Sıradaki Soru Sayacı ---
      Item {
        width: parent.width
        height: 22

        LexisGlyph {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          pixelSize: 15
          fullWord: true
          inkColor: Commons.Color.popups.text
          dotColor: Commons.Color.accent
        }

        Text {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: {
            if (!root.service) return ""
            if (root.service.isMuted) {
              return Theme.t(root.lang, "Susturuldu · ", "Muted · ") + Theme.formatCountdown(root.service.nextInSeconds, root.lang)
            }
            return Theme.t(root.lang, "Sıradaki: ", "Next in ") + Theme.formatCountdown(root.service.nextInSeconds, root.lang)
          }
          font.family: Style.font.family
          font.pixelSize: 11
          color: Theme.withAlpha(Commons.Color.popups.text, 0.58)
        }
      }

      // --- Günlük Hedef İlerlemesi ---
      Column {
        width: parent.width
        spacing: 5

        Item {
          width: parent.width
          height: 18

          Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: Theme.t(root.lang, "Bugün", "Today")
            font.family: Style.font.family
            font.pixelSize: 12
            color: Theme.withAlpha(Commons.Color.popups.text, 0.68)
          }

          Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.answered + " / " + root.goal
            font.family: "Monospace"
            font.pixelSize: 12
            font.weight: Font.DemiBold
            color: Commons.Color.popups.text
          }
        }

        Rectangle {
          width: parent.width
          height: 5
          radius: 3
          color: Theme.withAlpha(Commons.Color.popups.text, 0.12)

          Rectangle {
            width: Math.max(0, Math.round(parent.width * root.goalRatio))
            height: parent.height
            radius: 3
            color: Commons.Color.accent
          }
        }
      }

      // --- + Hızlı Kelime Ekle ---
      Rectangle {
        width: parent.width
        height: 32
        radius: Math.max(6, Style.cornerRadius)
        color: Theme.withAlpha(Commons.Color.popups.text, 0.06)
        border.width: (quickInput.activeFocus || (root.kbActive && root.kbIndex === 0)) ? 1 : 1
        border.color: (quickInput.activeFocus || (root.kbActive && root.kbIndex === 0))
          ? Commons.Color.accent
          : Theme.withAlpha(Commons.Color.popups.text, 0.14)

        Text {
          visible: quickInput.text.length === 0 && root.quickNotice.length === 0
          anchors.left: parent.left
          anchors.leftMargin: 10
          anchors.verticalCenter: parent.verticalCenter
          text: Theme.t(root.lang, "+ Hızlı kelime ekle…", "+ Quick add word…")
          font.family: Style.font.family
          font.pixelSize: 12
          color: Theme.withAlpha(Commons.Color.popups.text, 0.46)
        }

        Text {
          visible: quickInput.text.length === 0 && root.quickNotice.length > 0
          anchors.left: parent.left
          anchors.leftMargin: 10
          anchors.verticalCenter: parent.verticalCenter
          text: root.quickNotice
          font.family: Style.font.family
          font.pixelSize: 12
          color: Commons.Color.accent
        }

        TextInput {
          id: quickInput
          anchors.fill: parent
          anchors.leftMargin: 10
          anchors.rightMargin: 10
          verticalAlignment: TextInput.AlignVCenter
          clip: true
          font.family: Style.font.family
          font.pixelSize: 12
          color: Commons.Color.popups.text
          selectionColor: Commons.Color.accent
          selectedTextColor: root.tokens.primaryInk || "#1d2021"

          Keys.onReturnPressed: root.submitQuickWord()
          Keys.onEnterPressed: root.submitQuickWord()
          Keys.onEscapePressed: {
            quickInput.focus = false
            keyCatcher.forceActiveFocus()
          }
        }
      }

      // --- Birincil 2 Sütunlu Eylemler: Şimdi Sor + 1 Saat Sustur ---
      Row {
        width: parent.width
        spacing: 8

        Rectangle {
          readonly property bool kbSel: root.kbActive && root.kbIndex === 1
          width: (parent.width - 8) / 2
          height: 32
          radius: Math.max(6, Style.cornerRadius)
          color: (askArea.containsMouse || kbSel)
            ? Theme.withAlpha(Commons.Color.accent, 0.88)
            : Commons.Color.accent
          border.width: kbSel ? 1 : 0
          border.color: Commons.Color.popups.text

          Text {
            anchors.centerIn: parent
            text: Theme.t(root.lang, "Şimdi sor", "Ask now")
            font.family: Style.font.family
            font.pixelSize: 12
            font.weight: Font.DemiBold
            color: root.tokens.primaryInk || "#1d2021"
          }

          MouseArea {
            id: askArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              root.close()
              if (root.service) root.service.askNow(0)
            }
          }
        }

        Rectangle {
          readonly property bool kbSel: root.kbActive && root.kbIndex === 2
          width: (parent.width - 8) / 2
          height: 32
          radius: Math.max(6, Style.cornerRadius)
          color: (muteArea.containsMouse || kbSel)
            ? Theme.withAlpha(Commons.Color.popups.text, 0.14)
            : Theme.withAlpha(Commons.Color.popups.text, 0.07)
          border.width: kbSel ? 1 : 0
          border.color: Commons.Color.popups.text

          Text {
            anchors.centerIn: parent
            text: (root.service && root.service.isMuted)
              ? Theme.t(root.lang, "Devam et", "Unmute")
              : Theme.t(root.lang, "1 sa sustur", "Mute 1h")
            font.family: Style.font.family
            font.pixelSize: 12
            font.weight: Font.Medium
            color: Commons.Color.popups.text
          }

          MouseArea {
            id: muteArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              if (!root.service) return
              root.service.muteFor(root.service.isMuted ? 0 : 60)
            }
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: Theme.withAlpha(Commons.Color.popups.text, 0.10)
      }

      // --- Panel Navigasyon Bağlantıları ---
      Column {
        width: parent.width
        spacing: 2

        Repeater {
          model: [
            { tab: "today", idx: 3, label: Theme.t(root.lang, "Lexis panelini aç…", "Open Lexis panel…") },
            { tab: "words", idx: 4, label: Theme.t(root.lang, "Kelimeler…", "Words…") },
            { tab: "translate", idx: 5, label: Theme.t(root.lang, "Çeviri…", "Translate…") },
            { tab: "settings", idx: 6, label: Theme.t(root.lang, "Ayarlar…", "Settings…") }
          ]
          delegate: Rectangle {
            readonly property bool kbSel: root.kbActive && root.kbIndex === modelData.idx
            width: menuCol.width
            height: 28
            radius: 6
            color: (navLinkArea.containsMouse || kbSel)
              ? Theme.withAlpha(Commons.Color.popups.text, 0.11)
              : "transparent"

            Text {
              anchors.left: parent.left
              anchors.leftMargin: 8
              anchors.verticalCenter: parent.verticalCenter
              text: modelData.label
              font.family: Style.font.family
              font.pixelSize: 12
              color: Commons.Color.popups.text
            }

            MouseArea {
              id: navLinkArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                root.close()
                if (root.service) root.service.openMainPanel(modelData.tab)
              }
            }
          }
        }
      }
    }
  }
}
