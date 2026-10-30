import QtQuick
import qs.Commons
import "../Theme.js" as Theme

// Çeviri sekmesi: targetLang <-> meaningLang çift yönlü hibrit çeviri.
// Enter çevirir, Shift+Enter yeni satır açar; tek kelime/kısa ifade için "+ Listeye ekle" sunar.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  property string addedCandidateFeedback: ""

  readonly property bool isEditingText: trEdit.activeFocus

  function releaseTextFocus() {
    if (!trEdit.activeFocus) return false
    trEdit.focus = false
    return true
  }

  function dismissOverlay() { return false }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property string targetLang: service && service.settings ? String(service.settings.targetLang || "English") : "English"
  readonly property string meaningLang: service && service.settings ? String(service.settings.meaningLang || "Turkish") : "Turkish"
  readonly property var result: service ? service.lastTranslation : null
  readonly property bool isStale: !!(result && result.text && String(trEdit.text || "").trim() !== String(result.text))

  function triggerTranslate() {
    var txt = String(trEdit.text || "").trim()
    if (!txt || !service) return
    addedCandidateFeedback = ""
    service.translateText(txt)
  }

  Column {
    anchors.fill: parent
    anchors.margins: 34
    spacing: 16

    Column {
      width: parent.width
      spacing: 4

      Text {
        text: Theme.t(root.lang, "Çevir", "Translate")
        font.family: root.fontFamily
        font.pixelSize: 22
        font.weight: Font.DemiBold
        color: root.tokens.ink || "#ebdbb2"
      }

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: root.targetLang + " ↔ " + root.meaningLang + " · "
          + Theme.t(
            root.lang,
            "Enter çevirir, Shift+Enter yeni satıra geçer.",
            "Press Enter to translate, Shift+Enter for a new line."
          )
        font.family: root.fontFamily
        font.pixelSize: 13
        color: root.tokens.muted || "#a89984"
      }
    }

    // Metin girişi
    Rectangle {
      width: parent.width
      height: 112
      radius: 8
      color: root.tokens.surface || "#32302f"
      border.width: 1
      border.color: trEdit.activeFocus
        ? (root.tokens.accent || "#fe8019")
        : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

      Text {
        visible: trEdit.text.length === 0
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 12
        text: Theme.t(root.lang, "Kelime veya cümle yaz…", "Type a word, phrase, or sentence…")
        font.family: root.fontFamily
        font.pixelSize: 13
        color: root.tokens.muted || "#a89984"
      }

      Flickable {
        anchors.fill: parent
        anchors.margins: 12
        contentHeight: trEdit.implicitHeight
        clip: true

        TextEdit {
          id: trEdit
          width: parent.width
          wrapMode: TextEdit.Wrap
          font.family: root.fontFamily
          font.pixelSize: 14
          color: root.tokens.ink || "#ebdbb2"
          selectionColor: root.tokens.accent || "#fe8019"
          selectedTextColor: root.tokens.primaryInk || "#1d2021"

          Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
              event.accepted = true
              root.triggerTranslate()
            } else if (event.key === Qt.Key_Escape) {
              event.accepted = true
              trEdit.focus = false
            }
          }
        }
      }
    }

    Row {
      spacing: 10

      Rectangle {
        width: trBtnLbl.implicitWidth + 28
        height: 34
        radius: 7
        color: trBtnArea.containsMouse
          ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
          : (root.tokens.primaryBg || "#fe8019")

        Text {
          id: trBtnLbl
          anchors.centerIn: parent
          text: (root.service && root.service.translating)
            ? Theme.t(root.lang, "Çevriliyor…", "Translating…")
            : Theme.t(root.lang, "Çevir", "Translate")
          font.family: root.fontFamily
          font.pixelSize: 13
          font.weight: Font.DemiBold
          color: root.tokens.primaryInk || "#1d2021"
        }

        MouseArea {
          id: trBtnArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.triggerTranslate()
        }
      }
    }

    // Çeviri çıktısı
    Rectangle {
      visible: root.result !== null && String(trEdit.text || "").trim().length > 0
      width: parent.width
      height: visible ? (outCol.implicitHeight + 28) : 0
      radius: 8
      color: root.tokens.surface || "#32302f"
      border.width: 1
      border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)
      opacity: root.isStale ? 0.55 : 1.0

      Column {
        id: outCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 10

        Flow {
          width: parent.width
          spacing: 8

          Text {
            visible: !!(root.result && !root.result.error)
            text: {
              if (!root.result) return ""
              var dir = root.result.source === "target"
                ? (root.targetLang + " → " + root.meaningLang)
                : (root.meaningLang + " → " + root.targetLang)
              var srcBadge = root.result.via === "ai"
                ? "AI"
                : Theme.t(root.lang, "Ücretsiz Sözlük", "Free Dictionary")
              return dir + " · " + srcBadge
            }
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: Font.DemiBold
            color: root.tokens.muted || "#a89984"
          }

          Text {
            visible: root.isStale
            text: Theme.t(root.lang, "(güncellemek için Enter)", "(press Enter to refresh)")
            font.family: root.fontFamily
            font.pixelSize: 11
            color: root.tokens.muted || "#a89984"
          }
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: {
            if (!root.result) return ""
            if (root.result.error) return String(root.result.error)
            return String(root.result.translation || "")
          }
          font.family: root.fontFamily
          font.pixelSize: 16
          color: (root.result && root.result.error)
            ? (root.tokens.danger || "#fb4934")
            : (root.tokens.ink || "#ebdbb2")
        }

        // + Listeye ekle adayı
        Row {
          visible: !!(root.result && !root.result.error && root.result.candidateWord)
          width: parent.width
          spacing: 10

          Rectangle {
            width: Math.min(outCol.width, addCandTxt.implicitWidth + 24)
            height: 28
            radius: 6
            color: addCandArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface2 || "#3c3836")
            border.width: 1
            border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

            Text {
              id: addCandTxt
              anchors.centerIn: parent
              width: Math.min(implicitWidth, parent.width - 20)
              elide: Text.ElideRight
              text: root.addedCandidateFeedback
                ? root.addedCandidateFeedback
                : ("+ " + Theme.t(root.lang, "Listeye ekle: ", "Add to deck: ") + String(root.result ? (root.result.candidateWord || "") : ""))
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.addedCandidateFeedback
                ? (root.tokens.accent || "#fe8019")
                : (root.tokens.ink || "#ebdbb2")
            }

            MouseArea {
              id: addCandArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (!root.service || !root.result || !root.result.candidateWord) return
                root.service.addWordQuick(String(root.result.candidateWord), function(res) {
                  root.addedCandidateFeedback = (res && res.duplicate)
                    ? Theme.t(root.lang, "Zaten listede", "Already in deck")
                    : Theme.t(root.lang, "✓ Listeye eklendi", "✓ Added to deck")
                })
              }
            }
          }
        }
      }
    }
  }
}
