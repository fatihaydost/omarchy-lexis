import QtQuick
import qs.Commons
import "../Theme.js" as Theme

// Bugün sekmesi: sakin selamlama, günlük soru hedefi çubuğu, sıradaki soru geri sayımı,
// Şimdi sor / 1 saat sustur eylemleri, son eklenen 4 kelime ve seçili metin kısayolu ipucu.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  readonly property bool isEditingText: false

  function releaseTextFocus() { return false }
  function dismissOverlay() { return false }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var today: service && service.todayData ? service.todayData : ({})
  readonly property int answered: Number(today.answered) || 0
  readonly property int goal: Math.max(1, Number(today.goal) || 50)
  readonly property int totalWords: Number(today.totalWords) || 0
  readonly property real ratio: Math.max(0.0, Math.min(1.0, answered / goal))
  readonly property var recentList: today.recent ? today.recent : []

  signal jumpToWord(int wordId)
  signal jumpToLists()

  Row {
    anchors.fill: parent
    anchors.margins: 34
    spacing: 38

    // --- SOL SÜTUN: Selamlama + Günlük İlerleme + Birincil Eylemler ---
    Column {
      width: Math.round((parent.width - 38) * 0.54)
      spacing: 22

      Column {
        width: parent.width
        spacing: 6

        Text {
          text: Theme.greetingForNow(root.lang)
          font.family: root.fontFamily
          font.pixelSize: 24
          font.weight: Font.DemiBold
          color: root.tokens.ink || "#ebdbb2"
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: {
            if (root.totalWords === 0) {
              return Theme.t(
                root.lang,
                "Henüz kelime destesi yok. Başlangıç destesini yükleyebilir veya kendi CSV/PDF listeni aktarabilirsin.",
                "No words loaded yet. Load the starter deck or import your own CSV/PDF list to begin."
              )
            }
            if (root.service && root.service.isMuted) {
              return Theme.t(root.lang, "Sorular geçici olarak susturuldu · ", "Questions paused · ")
                + Theme.formatCountdown(root.service.nextInSeconds, root.lang)
            }
            if (root.service && root.service.activeQuestion) {
              return Theme.t(root.lang, "Sağ üstte bir kart cevabını bekliyor.", "A card is waiting for your answer at the top-right.")
            }
            return Theme.t(root.lang, "Sıradaki soru ", "Next question in ")
              + Theme.formatCountdown(root.service ? root.service.nextInSeconds : 300, root.lang)
              + Theme.t(root.lang, " sonra sağ üstte belirecek.", " at the top-right corner.")
          }
          font.family: root.fontFamily
          font.pixelSize: 13
          color: root.tokens.secondary || "#d5c4a1"
        }
      }

      // Günlük hedef göstergesi (kutu yok, tipografik hiyerarşi + ince ilerleme çizgisi)
      Column {
        width: parent.width
        spacing: 10

        Flow {
          width: parent.width
          spacing: 8

          Text {
            text: String(root.answered)
            font.family: root.fontFamily
            font.pixelSize: 42
            font.weight: Font.Bold
            color: root.tokens.ink || "#ebdbb2"
          }

          Text {
            topPadding: 20
            text: "/ " + root.goal + " " + Theme.t(root.lang, "bugün cevaplanan", "answered today")
            font.family: root.fontFamily
            font.pixelSize: 14
            color: root.tokens.muted || "#a89984"
          }
        }

        Rectangle {
          width: parent.width
          height: 6
          radius: 3
          color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

          Rectangle {
            width: Math.max(0, Math.round(parent.width * root.ratio))
            height: parent.height
            radius: 3
            color: root.tokens.accent || "#fe8019"
          }
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: {
            var rem = Math.max(0, root.goal - root.answered)
            if (rem === 0) return Theme.t(root.lang, "Günlük hedef tamamlandı.", "Daily goal reached.")
            return rem + " " + Theme.t(root.lang, "soru kaldı · toplam ", "left for today · ")
              + root.totalWords + " " + Theme.t(root.lang, "aktif kelime", "active words")
          }
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.muted || "#a89984"
        }
      }

      // Birincil Eylemler (Flow sayesinde uzun etiketler sağ sütuna taşmadan alt satıra sarılır)
      Flow {
        width: parent.width
        spacing: 10

        Rectangle {
          width: askTxt.implicitWidth + 32
          height: 36
          radius: 8
          color: askBtn.containsMouse
            ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
            : (root.tokens.primaryBg || "#fe8019")

          Text {
            id: askTxt
            anchors.centerIn: parent
            text: root.totalWords === 0
              ? Theme.t(root.lang, "Başlangıç destesini yükle", "Load starter deck")
              : Theme.t(root.lang, "Şimdi sor", "Ask now")
            font.family: root.fontFamily
            font.pixelSize: 13
            font.weight: Font.DemiBold
            color: root.tokens.primaryInk || "#1d2021"
          }

          MouseArea {
            id: askBtn
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              if (!root.service) return
              if (root.totalWords === 0) {
                root.service.loadStarterDeck(null)
              } else {
                root.service.askNow(0)
              }
            }
          }
        }

        Rectangle {
          width: muteTxt.implicitWidth + 28
          height: 36
          radius: 8
          color: muteBtn.containsMouse
            ? (root.tokens.raised || "#504945")
            : (root.tokens.surface || "#32302f")
          border.width: 1
          border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

          Text {
            id: muteTxt
            anchors.centerIn: parent
            text: (root.service && root.service.isMuted)
              ? Theme.t(root.lang, "Susturmayı kaldır", "Resume questions")
              : Theme.t(root.lang, "1 saat sustur", "Mute for 1 hour")
            font.family: root.fontFamily
            font.pixelSize: 13
            color: root.tokens.ink || "#ebdbb2"
          }

          MouseArea {
            id: muteBtn
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              if (!root.service) return
              root.service.muteFor(root.service.isMuted ? 0 : 60)
            }
          }
        }

        Rectangle {
          visible: root.totalWords === 0
          width: impTxt.implicitWidth + 28
          height: 36
          radius: 8
          color: impBtn.containsMouse
            ? (root.tokens.raised || "#504945")
            : "transparent"
          border.width: 1
          border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.18)

          Text {
            id: impTxt
            anchors.centerIn: parent
            text: Theme.t(root.lang, "CSV / PDF aktar…", "Import CSV / PDF…")
            font.family: root.fontFamily
            font.pixelSize: 13
            color: root.tokens.secondary || "#d5c4a1"
          }

          MouseArea {
            id: impBtn
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.jumpToLists()
          }
        }
      }

      // Soru aralığı: hızlı paneldeki ve Ayarlar'daki aynı değer
      Flow {
        visible: root.totalWords > 0
        width: parent.width
        spacing: 6

        Text {
          height: 28
          verticalAlignment: Text.AlignVCenter
          text: Theme.t(root.lang, "Soru aralığı", "Ask every")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.muted || "#a89984"
        }

        Repeater {
          model: [3, 5, 10, 15, 30]
          delegate: Rectangle {
            readonly property bool sel: root.service && root.service.settings
              && (Number(root.service.settings.intervalMin) || 5) === modelData
            width: ivTxt.implicitWidth + 18
            height: 28
            radius: 7
            color: sel
              ? (root.tokens.primaryBg || "#fe8019")
              : (ivArea.containsMouse ? (root.tokens.raised || "#504945") : (root.tokens.surface || "#32302f"))
            border.width: sel ? 0 : 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: ivTxt
              anchors.centerIn: parent
              text: modelData + Theme.t(root.lang, " dk", " min")
              font.family: root.fontFamily
              font.pixelSize: 12
              font.weight: parent.sel ? Font.DemiBold : Font.Normal
              color: parent.sel ? (root.tokens.primaryInk || "#1d2021") : (root.tokens.ink || "#ebdbb2")
            }

            MouseArea {
              id: ivArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: if (root.service && !parent.sel) root.service.saveSettings({ intervalMin: modelData })
            }
          }
        }
      }
    }

    Rectangle {
      width: 1
      height: parent.height
      color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
    }

    // --- SAĞ SÜTUN: Son Eklenenler + Kısayol İpucu ---
    Column {
      width: parent.width - Math.round((parent.width - 38) * 0.54) - 77
      spacing: 16

      Text {
        text: Theme.t(root.lang, "SON EKLENENLER", "RECENTLY ADDED")
        font.family: root.fontFamily
        font.pixelSize: 11
        font.weight: Font.DemiBold
        font.letterSpacing: 0.8
        color: root.tokens.muted || "#a89984"
      }

      Text {
        visible: root.recentList.length === 0
        width: parent.width
        wrapMode: Text.WordWrap
        text: Theme.t(
          root.lang,
          "Henüz eklenen kelime yok.",
          "No words added yet."
        )
        font.family: root.fontFamily
        font.pixelSize: 13
        color: root.tokens.muted || "#a89984"
      }

      Column {
        width: parent.width
        spacing: 2

        Repeater {
          model: root.recentList
          delegate: Rectangle {
            width: parent.width
            height: 36
            radius: 7
            color: recArea.containsMouse
              ? (root.tokens.surface || "#32302f")
              : "transparent"

            Text {
              anchors.left: parent.left
              anchors.leftMargin: 8
              anchors.verticalCenter: parent.verticalCenter
              width: parent.width - 130
              elide: Text.ElideRight
              text: String(modelData.word || "")
              font.family: root.fontFamily
              font.pixelSize: 14
              font.weight: Font.Medium
              color: root.tokens.ink || "#ebdbb2"
            }

            Text {
              anchors.right: parent.right
              anchors.rightMargin: 8
              anchors.verticalCenter: parent.verticalCenter
              text: String(modelData.how || "") + " · " + String(modelData.when || "")
              font.family: root.fontFamily
              font.pixelSize: 11
              color: root.tokens.muted || "#a89984"
            }

            MouseArea {
              id: recArea
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

      Rectangle {
        width: parent.width
        height: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        lineHeight: 1.35
        textFormat: Text.StyledText
        text: Theme.t(
          root.lang,
          "Herhangi bir uygulamada kelimeyi seçip <b>SUPER + SHIFT + X</b> ile listene atabilirsin. Anlamını ve örnek cümlesini ücretsiz sözlükten (gerekirse bağlı AI ile) kendisi tamamlar.",
          "Select any word in a browser, PDF, or editor and press <b>SUPER + SHIFT + X</b> to capture it. Lexis fills its meaning and example sentence automatically."
        )
        font.family: root.fontFamily
        font.pixelSize: 12
        color: root.tokens.muted || "#a89984"
      }
    }
  }
}
