import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui
import "Bridge.js" as Bridge
import "Theme.js" as Theme
import "components"

// Omarchy üst bar bileşeni (monitör başına omarchy.bar tarafından oluşturulur).
// "l." marka işaretini ve isteğe bağlı günlük cevaplanan/hedef sayacını sabit genişlikte çizer.
Ui.BarWidget {
  id: root
  moduleName: "io.github.fatihaydost.lexis"

  property var liveService: null
  readonly property var svc: liveService || (root.bar && typeof root.bar.serviceFor === "function"
    ? root.bar.serviceFor("io.github.fatihaydost.lexis")
    : null)
  readonly property string screenName: Bridge.windowScreenName(QsWindow.window)

  property var _bridgeCb: null

  Component.onCompleted: {
    Bridge.registerBarWidget(root)
    _bridgeCb = function(s) { root.liveService = s }
    Bridge.subscribe(_bridgeCb)
  }

  Component.onDestruction: {
    if (_bridgeCb) Bridge.unsubscribe(_bridgeCb)
    Bridge.unregisterBarWidget(root)
  }

  readonly property bool opened: popout.opened
  readonly property bool popoutSwitchClosing: popout.popoutSwitchClosing

  function open() { popout.open() }
  function close() { popout.close() }
  function togglePanel() { popout.toggle() }
  function closeForPopoutSwitch() { popout.closeForPopoutSwitch() }

  readonly property string lang: svc ? svc.lang : "en"
  readonly property int answered: svc && svc.todayData ? (Number(svc.todayData.answered) || 0) : 0
  readonly property int goal: svc && svc.todayData ? Math.max(1, Number(svc.todayData.goal) || 50) : 50
  readonly property bool showBarPref: root.setting("showProgressInBar", true) !== false
  readonly property bool showAppPref: !(svc && svc.settings && svc.settings.showProgressInBar === false)
  readonly property bool progressVisible: showBarPref && showAppPref
  readonly property string counterText: answered + "/" + goal
  readonly property string metricsTemplate: (answered >= 100 || goal >= 100) ? "999/999" : "99/99"

  readonly property string tooltipText: {
    if (!svc) return "Lexis"
    var statusPart = svc.isMuted
      ? Theme.t(lang, "Susturuldu", "Muted")
      : (Theme.t(lang, "Sıradaki: ", "Next in ") + Theme.formatCountdown(svc.nextInSeconds, lang))
    return "Lexis — " + counterText + " · " + statusPart
  }

  readonly property color fgColor: root.bar ? root.bar.barForeground : Commons.Color.foreground
  readonly property color accentColor: Commons.Color.accent

  TextMetrics {
    id: counterMetrics
    font.family: root.bar ? root.bar.fontFamily : Style.font.family
    font.pixelSize: Style.font.body
    text: root.metricsTemplate
  }

  readonly property real reservedContentWidth: progressVisible
    ? (glyphMark.implicitWidth + Style.space(5) + Math.ceil(counterMetrics.width))
    : glyphMark.implicitWidth

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarPopout {
    id: popout
    bar: root.bar
    anchorItem: button
    hostWidget: root
    service: root.svc
  }

  Ui.WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: root.tooltipText
    labelVisible: false
    hasVisualContent: true
    active: root.opened
    useActiveColor: false
    fixedWidth: root.vertical
      ? -1
      : Math.ceil(root.reservedContentWidth + Style.spaceReal(horizontalMargin) * 2)
    fixedHeight: root.vertical
      ? Math.ceil(contentRow.implicitHeight + Style.spaceReal(verticalPadding) * 2)
      : -1

    onPressed: function(b) {
      if (b === Qt.MiddleButton) {
        if (root.svc) root.svc.askNow(0)
      } else if (b === Qt.RightButton) {
        root.close()
        if (root.svc) root.svc.openMainPanel("today")
      } else {
        root.togglePanel()
      }
    }

    Row {
      id: contentRow
      anchors.centerIn: parent
      spacing: Style.space(5)

      LexisGlyph {
        id: glyphMark
        anchors.verticalCenter: parent.verticalCenter
        pixelSize: Style.font.body
        inkColor: root.fgColor
        dotColor: root.accentColor
        fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
      }

      Text {
        visible: root.progressVisible && !root.vertical
        width: Math.ceil(counterMetrics.width)
        anchors.verticalCenter: parent.verticalCenter
        horizontalAlignment: Text.AlignLeft
        text: root.counterText
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.body
        renderType: Text.NativeRendering
        color: root.fgColor
      }
    }
  }
}
