import QtQuick
import qs.Commons
import "../Theme.js" as Theme

// İstatistikler sekmesi: 3 ana sayaç (bugün cevaplanan, 30 günlük doğruluk, oturan kelime),
// 30 günlük 10x3 etkinlik ızgarası, tıklanabilir en çok takılan kelimeler duvarı ve
// 4 soru tipine göre doğruluk çubukları.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  property int hoveredDayIndex: -1

  readonly property bool isEditingText: false

  function releaseTextFocus() { return false }
  function dismissOverlay() { return false }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var stats: service && service.statsData ? service.statsData : ({})

  readonly property int answeredToday: Number(stats.answeredToday) || 0
  readonly property int accuracy: Number(stats.accuracy) || 0
  readonly property int settled: Number(stats.settled) || 0
  readonly property int totalWords: Number(stats.totalWords) || 0
  readonly property var hardest: stats.hardest ? stats.hardest : []
  readonly property var days: {
    var src = stats.days ? stats.days : []
    if (src.length === 30) return src
    var out = []
    for (var i = 0; i < 30; i++) out.push(i < src.length ? (Number(src[i]) || 0) : 0)
    return out
  }
  readonly property var byType: stats.byType ? stats.byType : ({})

  readonly property int maxDayCount: {
    var m = 1
    for (var i = 0; i < days.length; i++) {
      var v = Number(days[i]) || 0
      if (v > m) m = v
    }
    return m
  }

  readonly property int maxMissCount: {
    var m = 1
    for (var i = 0; i < hardest.length; i++) {
      var v = hardest[i] && hardest[i].misses ? Number(hardest[i].misses) : 0
      if (v > m) m = v
    }
    return m
  }

  signal jumpToWord(int wordId)

  function _dayHoverLabel(idx) {
    if (idx < 0 || idx >= days.length) {
      var sum = 0
      for (var i = 0; i < days.length; i++) sum += Number(days[i]) || 0
      return sum + " " + Theme.t(lang, "cevap (son 30 gün)", "answers in last 30 days")
    }
    var ago = 29 - idx
    var cnt = Number(days[idx]) || 0
    var whenTxt = ago === 0
      ? Theme.t(lang, "Bugün", "Today")
      : (ago === 1
        ? Theme.t(lang, "Dün", "Yesterday")
        : (ago + " " + Theme.t(lang, "gün önce", "days ago")))
    return whenTxt + " · " + cnt + " " + Theme.t(lang, "cevap", cnt === 1 ? "answer" : "answers")
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
      spacing: 24

      // Başlık
      Column {
        width: parent.width
        spacing: 4

        Text {
          text: Theme.t(root.lang, "İstatistikler", "Statistics")
          font.family: root.fontFamily
          font.pixelSize: 22
          font.weight: Font.DemiBold
          color: root.tokens.ink || "#ebdbb2"
        }

        Text {
          text: Theme.t(
            root.lang,
            "Son 30 günlük aralıklı tekrar performansı ve kutu dağılımı.",
            "Spaced-repetition activity and accuracy across the last 30 days."
          )
          font.family: root.fontFamily
          font.pixelSize: 13
          color: root.tokens.muted || "#a89984"
        }
      }

      // 3 Ana Sayaç
      Row {
        width: parent.width
        spacing: 24

        // 1) Bugün cevaplanan
        Column {
          width: Math.floor((parent.width - 50) / 3)
          spacing: 4

          Text {
            text: Theme.t(root.lang, "BUGÜN CEVAPLANAN", "ANSWERED TODAY")
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.7
            color: root.tokens.muted || "#a89984"
          }

          Text {
            text: String(root.answeredToday)
            font.family: root.fontFamily
            font.pixelSize: 34
            font.weight: Font.Bold
            color: root.tokens.ink || "#ebdbb2"
          }
        }

        Rectangle {
          width: 1
          height: 56
          color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
        }

        // 2) 30 günlük doğruluk
        Column {
          width: Math.floor((parent.width - 50) / 3)
          spacing: 4

          Text {
            text: Theme.t(root.lang, "30 GÜN DOĞRULUK", "30-DAY ACCURACY")
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.7
            color: root.tokens.muted || "#a89984"
          }

          Text {
            text: root.accuracy + "%"
            font.family: root.fontFamily
            font.pixelSize: 34
            font.weight: Font.Bold
            color: root.tokens.ink || "#ebdbb2"
          }
        }

        Rectangle {
          width: 1
          height: 56
          color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
        }

        // 3) Oturan kelimeler
        Column {
          width: Math.floor((parent.width - 50) / 3)
          spacing: 4

          Text {
            text: Theme.t(root.lang, "OTURAN KELİME", "SETTLED WORDS")
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.7
            color: root.tokens.muted || "#a89984"
          }

          Row {
            spacing: 6

            Text {
              text: String(root.settled)
              font.family: root.fontFamily
              font.pixelSize: 34
              font.weight: Font.Bold
              color: root.tokens.accent || "#fe8019"
            }

            Text {
              anchors.bottom: parent.bottom
              anchors.bottomMargin: 6
              text: "/ " + root.totalWords
              font.family: root.fontFamily
              font.pixelSize: 15
              color: root.tokens.muted || "#a89984"
            }
          }
        }
      }

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      // Alt iki sütun: Sol = 30 Günlük Izgara + En Çok Takılanlar, Sağ = 4 Soru Tipi Çubuğu
      Row {
        width: parent.width
        spacing: 36

        // SOL SÜTUN
        Column {
          width: Math.round((parent.width - 36) * 0.50)
          spacing: 22

          // 30 Günlük 10x3 Etkinlik Izgarası
          Column {
            width: parent.width
            spacing: 10

            Row {
              width: parent.width
              spacing: 10

              Text {
                text: Theme.t(root.lang, "SON 30 GÜN", "LAST 30 DAYS")
                font.family: root.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 0.7
                color: root.tokens.muted || "#a89984"
              }

              Text {
                text: "· " + root._dayHoverLabel(root.hoveredDayIndex)
                font.family: root.fontFamily
                font.pixelSize: 11
                color: root.tokens.secondary || "#d5c4a1"
              }
            }

            Grid {
              columns: 10
              spacing: 6

              Repeater {
                model: root.days
                delegate: Rectangle {
                  readonly property int cnt: Number(modelData) || 0
                  readonly property real intensity: cnt <= 0
                    ? 0.0
                    : Math.max(0.24, Math.min(1.0, cnt / root.maxDayCount))
                  width: 24
                  height: 24
                  radius: 5
                  color: cnt <= 0
                    ? (root.tokens.surface || "#32302f")
                    : Theme.withAlpha(root.tokens.accent || "#fe8019", intensity)
                  border.width: dayCellArea.containsMouse || index === 29 ? 1 : 0
                  border.color: dayCellArea.containsMouse
                    ? (root.tokens.ink || "#ebdbb2")
                    : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.22))

                  MouseArea {
                    id: dayCellArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: root.hoveredDayIndex = index
                    onExited: {
                      if (root.hoveredDayIndex === index) root.hoveredDayIndex = -1
                    }
                  }
                }
              }
            }
          }

          // En Çok Takılan Kelimeler Duvarı
          Column {
            width: parent.width
            spacing: 10

            Text {
              text: Theme.t(root.lang, "EN ÇOK TAKILANLAR", "MOST MISSED")
              font.family: root.fontFamily
              font.pixelSize: 11
              font.weight: Font.DemiBold
              font.letterSpacing: 0.7
              color: root.tokens.muted || "#a89984"
            }

            Text {
              visible: root.hardest.length === 0
              width: parent.width
              wrapMode: Text.WordWrap
              text: Theme.t(
                root.lang,
                "Son 30 günde yanlış cevaplanan kelime yok.",
                "No missed words in the last 30 days."
              )
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.muted || "#a89984"
            }

            Flow {
              visible: root.hardest.length > 0
              width: parent.width
              spacing: 8

              Repeater {
                model: root.hardest
                delegate: Rectangle {
                  id: missPill
                  readonly property int misses: Number(modelData.misses) || 1
                  readonly property int scaledPx: Math.round(
                    13 + 6 * Math.min(1.0, (misses - 1) / Math.max(1, root.maxMissCount - 1))
                  )
                  width: missRow.implicitWidth + 18
                  height: missRow.implicitHeight + 10
                  radius: 7
                  color: missArea.containsMouse
                    ? (root.tokens.raised || "#504945")
                    : (root.tokens.surface || "#32302f")
                  border.width: 1
                  border.color: missArea.containsMouse
                    ? (root.tokens.accent || "#fe8019")
                    : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

                  Row {
                    id: missRow
                    anchors.centerIn: parent
                    spacing: 5

                    Text {
                      text: String(modelData.word || "")
                      font.family: root.fontFamily
                      font.pixelSize: missPill.scaledPx
                      font.weight: Font.Medium
                      color: root.tokens.ink || "#ebdbb2"
                    }

                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      text: "×" + missPill.misses
                      font.family: "Monospace"
                      font.pixelSize: 11
                      color: root.tokens.danger || "#fb4934"
                    }
                  }

                  MouseArea {
                    id: missArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (modelData.id) root.jumpToWord(Number(modelData.id))
                    }
                  }
                }
              }
            }
          }
        }

        // SAĞ SÜTUN: 4 Soru Tipi Doğruluk Çubukları
        Column {
          width: parent.width - Math.round((parent.width - 36) * 0.50) - 36
          spacing: 14

          Text {
            text: Theme.t(root.lang, "SORU TİPİNE GÖRE DOĞRULUK", "ACCURACY BY QUESTION TYPE")
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.7
            color: root.tokens.muted || "#a89984"
          }

          Column {
            width: parent.width
            spacing: 16

            Repeater {
              model: [
                "choice_word_meaning",
                "choice_meaning_word",
                "type_word_meaning",
                "type_context"
              ]
              delegate: Column {
                id: qtypeBar
                readonly property bool hasData: root.byType && root.byType[modelData] !== undefined
                readonly property int pct: hasData ? Math.max(0, Math.min(100, Number(root.byType[modelData]) || 0)) : 0
                width: parent.width
                spacing: 6

                Item {
                  width: parent.width
                  height: 18

                  Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: Theme.qtypeLabel(modelData, root.lang)
                    font.family: root.fontFamily
                    font.pixelSize: 13
                    color: root.tokens.secondary || "#d5c4a1"
                  }

                  Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: qtypeBar.hasData ? (qtypeBar.pct + "%") : "—"
                    font.family: "Monospace"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: qtypeBar.hasData
                      ? (root.tokens.ink || "#ebdbb2")
                      : (root.tokens.muted || "#a89984")
                  }
                }

                Rectangle {
                  width: parent.width
                  height: 6
                  radius: 3
                  color: root.tokens.surface2 || "#3c3836"

                  Rectangle {
                    width: qtypeBar.hasData
                      ? Math.max(4, Math.round(parent.width * (qtypeBar.pct / 100.0)))
                      : 0
                    height: parent.height
                    radius: 3
                    color: root.tokens.accent || "#fe8019"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
