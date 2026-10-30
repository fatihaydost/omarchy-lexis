import QtQuick
import Quickshell
import Quickshell.Hyprland
import qs.Commons
import "../Theme.js" as Theme
import "../components"
import "../pages"

// Houra kardeş düzenli ana masaüstü penceresi (FloatingWindow, en çok 1040x680):
// Sabit min/max boyut ipuçları (`minimumSize === maximumSize`) sayesinde Hyprland özel windowrule
// gerekmeden pencereyi kendiliğinden yüzer ve ortalar; SUPER+W (killactive), Esc, Ctrl+W, Ctrl+Q
// ve × düğmesiyle temiz kapanır; zenity dosya seçicisi açıkken geçici gizlenip geri döner.
Item {
  id: root

  property var service: null
  property bool open: false
  property bool closingFromHost: false
  property bool _suspendedForDialog: false
  property string currentTab: "today" // "today" | "words" | "translate" | "stats" | "lists" | "settings"
  property string focusZone: "page"   // "page" | "sidebar"
  property bool sidebarOnCta: false
  property var openedScreen: null
  property int openedWorkspaceId: -1
  property string openedMonitorName: ""

  readonly property var tabOrder: ["today", "words", "translate", "stats", "lists", "settings"]
  readonly property var activePage: {
    if (currentTab === "words") return wordsPageItem
    if (currentTab === "translate") return translatePageItem
    if (currentTab === "stats") return statsPageItem
    if (currentTab === "lists") return listsPageItem
    if (currentTab === "settings") return settingsPageItem
    return todayPageItem
  }
  readonly property bool activePageEditing: !!(activePage && activePage.isEditingText)

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  property string fontFamily: Style.font.family

  readonly property int availW: openedScreen && openedScreen.width > 0 ? openedScreen.width : 1280
  readonly property int availH: openedScreen && openedScreen.height > 0 ? openedScreen.height : 800
  readonly property int targetWidth: Math.max(760, Math.min(Math.round(availW * 0.90), 1040))
  readonly property int targetHeight: Math.max(520, Math.min(Math.round(availH * 0.88), 680))

  onActivePageEditingChanged: {
    if (!activePageEditing && open && win.visible) {
      Qt.callLater(function() {
        if (root.open && !root.activePageEditing) keySink.forceActiveFocus()
      })
    }
  }

  // Zenity dosya seçicisi açıldığında pencereyi geçici gizle, kapandığında geri getir
  Connections {
    target: root.service
    function onNativeDialogOpenChanged() {
      if (!root.service) return
      if (root.service.nativeDialogOpen && root.open && win.visible) {
        root._suspendedForDialog = true
        root.closingFromHost = true
        win.visible = false
        root.closingFromHost = false
      } else if (!root.service.nativeDialogOpen && root._suspendedForDialog && root.open) {
        root._suspendedForDialog = false
        root.closingFromHost = false
        win.visible = true
        Qt.callLater(function() {
          if (root.open) keySink.forceActiveFocus()
        })
      }
    }
  }

  function _normalizeTabKey(rawKey) {
    var k = String(rawKey || "").trim().toLowerCase()
    if (tabOrder.indexOf(k) !== -1) return k
    return ""
  }

  function selectTabByIndex(idx, keepSidebarFocus) {
    if (idx < 0 || idx >= tabOrder.length) return
    if (activePage && activePage.releaseTextFocus) activePage.releaseTextFocus()
    sidebarOnCta = false
    currentTab = tabOrder[idx]
    focusZone = keepSidebarFocus ? "sidebar" : "page"
    keySink.forceActiveFocus()
  }

  function stepTab(delta, keepSidebarFocus) {
    var cur = tabOrder.indexOf(currentTab)
    if (cur < 0) cur = 0
    var next = (cur + delta + tabOrder.length) % tabOrder.length
    selectTabByIndex(next, !!keepSidebarFocus)
  }

  function stepSidebarItem(delta) {
    var total = tabOrder.length + 1 // 6 sekme + "Şimdi sor" CTA
    var cur = sidebarOnCta ? tabOrder.length : Math.max(0, tabOrder.indexOf(currentTab))
    var next = (cur + delta + total) % total
    if (next === tabOrder.length) {
      sidebarOnCta = true
    } else {
      sidebarOnCta = false
      currentTab = tabOrder[next]
    }
  }

  function jumpToWordDetail(wordId) {
    currentTab = "words"
    focusZone = "page"
    wordsPageItem.selectWordById(Number(wordId))
    keySink.forceActiveFocus()
  }

  function _resolveFocusedScreen() {
    var mon = Hyprland.focusedMonitor
    var screens = Quickshell.screens
    if (mon && screens) {
      for (var i = 0; i < screens.length; i++) {
        if (screens[i].name === mon.name) return screens[i]
      }
    }
    return screens && screens.length > 0 ? screens[0] : null
  }

  function _currentWorkspaceId() {
    return (Hyprland.focusedWorkspace && Hyprland.focusedWorkspace.id !== undefined)
      ? Number(Hyprland.focusedWorkspace.id)
      : -1
  }

  function isOnCurrentWorkspace() {
    if (!open || !win.visible) return false
    var curWs = _currentWorkspaceId()
    if (curWs !== -1 && openedWorkspaceId !== -1 && curWs !== openedWorkspaceId) return false
    return true
  }

  function showTab(tabKey) {
    var norm = _normalizeTabKey(tabKey)
    if (norm) currentTab = norm
    if (service) service.refreshSnapshot(null)
    var nextScreen = _resolveFocusedScreen()
    var nextMonName = nextScreen && nextScreen.name ? String(nextScreen.name) : ""
    var nextWsId = _currentWorkspaceId()
    var isFocusedNow = !!(Hyprland.activeToplevel && Hyprland.activeToplevel.title === "Lexis")
    var needRemap = win.visible && (
      !isFocusedNow
      || (nextWsId !== -1 && openedWorkspaceId !== -1 && nextWsId !== openedWorkspaceId)
      || (nextMonName !== "" && openedMonitorName !== "" && nextMonName !== openedMonitorName)
    )

    if (nextScreen) openedScreen = nextScreen
    openedMonitorName = nextMonName
    openedWorkspaceId = nextWsId
    _suspendedForDialog = false
    sidebarOnCta = false
    focusZone = "page"
    open = true

    if (needRemap) {
      closingFromHost = true
      win.visible = false
      closingFromHost = false
      Qt.callLater(function() {
        if (!root.open) return
        root.closingFromHost = false
        win.visible = true
        Qt.callLater(function() {
          if (root.open) keySink.forceActiveFocus()
        })
      })
    } else {
      closingFromHost = false
      win.visible = true
      Qt.callLater(function() {
        if (root.open) keySink.forceActiveFocus()
      })
    }
  }

  function hideWindow() {
    if (activePage && activePage.releaseTextFocus) activePage.releaseTextFocus()
    _suspendedForDialog = false
    sidebarOnCta = false
    closingFromHost = true
    open = false
    win.visible = false
    closingFromHost = false
  }

  FloatingWindow {
    id: win
    visible: false
    screen: root.openedScreen
    title: "Lexis"
    implicitWidth: root.targetWidth
    implicitHeight: root.targetHeight
    minimumSize: Qt.size(root.targetWidth, root.targetHeight)
    maximumSize: Qt.size(root.targetWidth, root.targetHeight)
    color: root.tokens.win || "#282828"

    onClosed: {
      if (!root.closingFromHost) root.hideWindow()
    }

    onVisibleChanged: {
      if (!visible && !root.closingFromHost && !root._suspendedForDialog) {
        root.hideWindow()
      }
    }

    Rectangle {
      anchors.fill: parent
      color: root.tokens.win || "#282828"
      clip: true

      FocusScope {
        id: panelKeyScope
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem

        Item {
          id: keySink
          focus: true
        }

        Keys.onPressed: function(event) {
          var k = event.key
          var mods = event.modifiers

          // 1) Standart pencere kapatma kısayolları: Ctrl+W / Ctrl+Q
          if ((mods & Qt.ControlModifier) && (k === Qt.Key_W || k === Qt.Key_Q)) {
            event.accepted = true
            root.hideWindow()
            return
          }

          // 2) Katmanlı Esc: odaklanmış metin kutusu -> açık alt görünüm -> pencereyi kapat
          if (k === Qt.Key_Escape) {
            event.accepted = true
            if (root.activePage && root.activePage.releaseTextFocus && root.activePage.releaseTextFocus()) {
              keySink.forceActiveFocus()
              return
            }
            if (root.activePage && root.activePage.dismissOverlay && root.activePage.dismissOverlay()) {
              keySink.forceActiveFocus()
              return
            }
            root.hideWindow()
            return
          }

          // 3) Standart Ctrl+Tab / Ctrl+Shift+Tab sekme geçişi
          if ((mods & Qt.ControlModifier) && !(mods & Qt.AltModifier)) {
            if (k === Qt.Key_Tab || k === Qt.Key_Backtab || k === Qt.Key_PageDown || k === Qt.Key_PageUp) {
              event.accepted = true
              var back = (k === Qt.Key_Backtab || k === Qt.Key_PageUp || (mods & Qt.ShiftModifier))
              root.stepTab(back ? -1 : 1, false)
              return
            }
          }

          // 4) Metin yazılırken normal tuşlara müdahale etme
          if (root.activePageEditing) return
          if (mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return

          // 5) Standart Tab / Shift+Tab: kenar çubuğu <-> sayfa geçişi
          if (k === Qt.Key_Tab || k === Qt.Key_Backtab) {
            event.accepted = true
            root.sidebarOnCta = false
            root.focusZone = root.focusZone === "sidebar" ? "page" : "sidebar"
            keySink.forceActiveFocus()
            return
          }

          // 6) Kenar çubuğu ok tuşları + Enter / Space
          if (root.focusZone === "sidebar") {
            if (k === Qt.Key_Down) { root.stepSidebarItem(1); event.accepted = true; return }
            if (k === Qt.Key_Up) { root.stepSidebarItem(-1); event.accepted = true; return }
            if (k === Qt.Key_Right) {
              root.sidebarOnCta = false
              root.focusZone = "page"
              event.accepted = true
              return
            }
            if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) {
              event.accepted = true
              if (root.sidebarOnCta) {
                if (root.service) root.service.askNow(0)
              } else {
                root.focusZone = "page"
              }
              return
            }
          } else if (k === Qt.Key_Left) {
            root.focusZone = "sidebar"
            root.sidebarOnCta = false
            event.accepted = true
          }
        }

        Row {
          anchors.fill: parent

          // --- SOL KENAR ÇUBUĞU (210px) ---
          Rectangle {
            width: 210
            height: parent.height
            color: root.tokens.sidebar || "#1d2021"

            Rectangle {
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              width: 1
              color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
            }

            // Üst marka ("lexis.") + 5 birincil sekme
            Column {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: 16
              spacing: 18

              Item {
                width: parent.width
                height: 26

                LexisGlyph {
                  anchors.left: parent.left
                  anchors.leftMargin: 4
                  anchors.verticalCenter: parent.verticalCenter
                  pixelSize: 17
                  fullWord: true
                  inkColor: root.tokens.ink || "#ebdbb2"
                  dotColor: root.tokens.accent || "#fe8019"
                  fontFamily: root.fontFamily
                }

                Rectangle {
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  width: 24
                  height: 24
                  radius: 7
                  color: closeHov.containsMouse
                    ? (root.tokens.raised || "#504945")
                    : "transparent"

                  Text {
                    anchors.centerIn: parent
                    text: "×"
                    font.family: root.fontFamily
                    font.pixelSize: 15
                    color: closeHov.containsMouse
                      ? (root.tokens.ink || "#ebdbb2")
                      : (root.tokens.muted || "#a89984")
                  }

                  MouseArea {
                    id: closeHov
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.hideWindow()
                  }
                }
              }

              Column {
                width: parent.width
                spacing: 4

                Repeater {
                  model: [
                    { key: "today", label: Theme.t(root.lang, "Bugün", "Today") },
                    { key: "words", label: Theme.t(root.lang, "Kelimeler", "Words") },
                    { key: "translate", label: Theme.t(root.lang, "Çevir", "Translate") },
                    { key: "stats", label: Theme.t(root.lang, "İstatistikler", "Statistics") },
                    { key: "lists", label: Theme.t(root.lang, "Listeler", "Lists") }
                  ]
                  delegate: Rectangle {
                    readonly property bool active: root.currentTab === modelData.key
                    readonly property bool sidebarFocused: active && root.focusZone === "sidebar" && !root.sidebarOnCta
                    width: parent.width
                    height: 35
                    radius: 8
                    color: active
                      ? (root.tokens.raised || "#504945")
                      : (navHov.containsMouse ? (root.tokens.card || "#32302f") : "transparent")
                    border.width: sidebarFocused ? 1 : 0
                    border.color: root.tokens.ink || "#ebdbb2"

                    Rectangle {
                      visible: parent.active
                      anchors.left: parent.left
                      anchors.leftMargin: 6
                      anchors.verticalCenter: parent.verticalCenter
                      width: 3
                      height: 15
                      radius: 2
                      color: root.tokens.accent || "#fe8019"
                    }

                    Text {
                      anchors.left: parent.left
                      anchors.leftMargin: 16
                      anchors.verticalCenter: parent.verticalCenter
                      text: modelData.label
                      font.family: root.fontFamily
                      font.pixelSize: 13
                      font.weight: parent.active ? Font.DemiBold : Font.Normal
                      color: parent.active
                        ? (root.tokens.ink || "#ebdbb2")
                        : (root.tokens.secondary || "#d5c4a1")
                    }

                    MouseArea {
                      id: navHov
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: {
                        if (root.activePage && root.activePage.releaseTextFocus) root.activePage.releaseTextFocus()
                        root.sidebarOnCta = false
                        root.currentTab = modelData.key
                        root.focusZone = "page"
                        keySink.forceActiveFocus()
                      }
                    }
                  }
                }
              }
            }

            // Alt Ayarlar sekmesi + "Şimdi sor" birincil eylemi
            Column {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              anchors.margins: 16
              spacing: 10

              Rectangle {
                readonly property bool active: root.currentTab === "settings"
                readonly property bool sidebarFocused: active && root.focusZone === "sidebar" && !root.sidebarOnCta
                width: parent.width
                height: 34
                radius: 8
                color: active
                  ? (root.tokens.raised || "#504945")
                  : (setHov.containsMouse ? (root.tokens.card || "#32302f") : "transparent")
                border.width: sidebarFocused ? 1 : 0
                border.color: root.tokens.ink || "#ebdbb2"

                Rectangle {
                  visible: parent.active
                  anchors.left: parent.left
                  anchors.leftMargin: 6
                  anchors.verticalCenter: parent.verticalCenter
                  width: 3
                  height: 14
                  radius: 2
                  color: root.tokens.accent || "#fe8019"
                }

                Text {
                  anchors.left: parent.left
                  anchors.leftMargin: 16
                  anchors.verticalCenter: parent.verticalCenter
                  text: Theme.t(root.lang, "Ayarlar", "Settings")
                  font.family: root.fontFamily
                  font.pixelSize: 13
                  font.weight: parent.active ? Font.DemiBold : Font.Normal
                  color: parent.active
                    ? (root.tokens.ink || "#ebdbb2")
                    : (root.tokens.secondary || "#d5c4a1")
                }

                MouseArea {
                  id: setHov
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.activePage && root.activePage.releaseTextFocus) root.activePage.releaseTextFocus()
                    root.sidebarOnCta = false
                    root.currentTab = "settings"
                    root.focusZone = "page"
                    keySink.forceActiveFocus()
                  }
                }
              }

              Rectangle {
                readonly property bool ctaFocused: root.focusZone === "sidebar" && root.sidebarOnCta
                width: parent.width
                height: 38
                radius: 9
                color: (ctaHov.containsMouse || ctaFocused)
                  ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
                  : (root.tokens.primaryBg || "#fe8019")
                border.width: ctaFocused ? 2 : 0
                border.color: root.tokens.ink || "#ebdbb2"

                Text {
                  anchors.centerIn: parent
                  text: Theme.t(root.lang, "Şimdi sor", "Ask now")
                  font.family: root.fontFamily
                  font.pixelSize: 13
                  font.weight: Font.DemiBold
                  color: root.tokens.primaryInk || "#1d2021"
                }

                MouseArea {
                  id: ctaHov
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (root.service) root.service.askNow(0)
                  }
                }
              }
            }
          }

          // --- AKTİF SAYFA İÇERİĞİ ---
          Item {
            width: parent.width - 210
            height: parent.height

            TodayPage {
              id: todayPageItem
              anchors.fill: parent
              visible: root.currentTab === "today"
              service: root.service
              fontFamily: root.fontFamily
              onJumpToWord: function(wordId) { root.jumpToWordDetail(wordId) }
              onJumpToLists: function() {
                root.currentTab = "lists"
                root.focusZone = "page"
                keySink.forceActiveFocus()
              }
            }

            WordsPage {
              id: wordsPageItem
              anchors.fill: parent
              visible: root.currentTab === "words"
              service: root.service
              fontFamily: root.fontFamily
            }

            TranslatePage {
              id: translatePageItem
              anchors.fill: parent
              visible: root.currentTab === "translate"
              service: root.service
              fontFamily: root.fontFamily
            }

            StatsPage {
              id: statsPageItem
              anchors.fill: parent
              visible: root.currentTab === "stats"
              service: root.service
              fontFamily: root.fontFamily
              onJumpToWord: function(wordId) { root.jumpToWordDetail(wordId) }
            }

            ListsPage {
              id: listsPageItem
              anchors.fill: parent
              visible: root.currentTab === "lists"
              service: root.service
              fontFamily: root.fontFamily
              onJumpToWord: function(wordId) { root.jumpToWordDetail(wordId) }
            }

            SettingsPage {
              id: settingsPageItem
              anchors.fill: parent
              visible: root.currentTab === "settings"
              service: root.service
              fontFamily: root.fontFamily
            }
          }
        }
      }
    }
  }
}
