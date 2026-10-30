import QtQuick
import qs.Commons
import "../Theme.js" as Theme

// Listeler sekmesi: kelime destelerini açıp kapatma, kaynak dosyayı açma,
// seçili destenin kelime tablosunu inceleme, CSV/PDF içe aktarma (10 satır önizleme +
// CSV 4 sütun eşleme seçicisi) ve 30 kelimelik başlangıç destesi yükleme.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family

  // Alt görünüm durumları: önizleme (import) veya tek liste inceleme
  property var previewData: null
  property string previewPath: ""
  property string importListName: ""
  property var importCols: [0, 1, 2, 3]
  property string importFeedback: ""

  property string inspectedListName: ""
  property string inspectedListSource: ""
  property var inspectedWords: []

  readonly property bool isEditingText: importNameInput.activeFocus

  function releaseTextFocus() {
    if (!importNameInput.activeFocus) return false
    importNameInput.focus = false
    return true
  }

  function dismissOverlay() {
    if (previewData !== null) {
      previewData = null
      previewPath = ""
      return true
    }
    if (inspectedListName !== "") {
      inspectedListName = ""
      inspectedListSource = ""
      inspectedWords = []
      return true
    }
    return false
  }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var lists: service && service.listsData ? service.listsData : []

  readonly property int maxCsvCols: {
    if (!previewData || !previewData.raw || previewData.raw.length === 0) return 6
    var m = 4
    for (var i = 0; i < previewData.raw.length; i++) {
      var r = previewData.raw[i]
      if (r && r.length > m) m = r.length
    }
    return Math.min(12, m)
  }

  signal jumpToWord(int wordId)

  function startImportPicker() {
    if (!service) return
    importFeedback = ""
    service.openImportDialog(function(chosenPath) {
      root.loadPreview(chosenPath, [0, 1, 2, 3], true)
    })
  }

  function loadPreview(filePath, cols, resetName) {
    if (!service || !filePath) return
    previewPath = String(filePath)
    importCols = cols
    service.previewImport(filePath, cols, function(res) {
      if (res && res.ok) {
        root.previewData = res
        if (resetName) root.importListName = String(res.name || "Imported")
      } else {
        root.previewData = null
        root.importFeedback = (res && res.error)
          ? String(res.error)
          : Theme.t(root.lang, "Dosya okunamadı.", "Could not read file.")
      }
    })
  }

  function cycleColumn(slotIndex, delta) {
    var copy = [importCols[0], importCols[1], importCols[2], importCols[3]]
    var minVal = slotIndex <= 1 ? 0 : -1
    var span = root.maxCsvCols - minVal
    if (span <= 0) return
    var cur = Number(copy[slotIndex])
    if (isNaN(cur)) cur = slotIndex
    var next = minVal + (((cur - minVal) + delta + span) % span)
    copy[slotIndex] = next
    loadPreview(previewPath, copy, false)
  }

  function _colSampleLabel(colIdx) {
    if (colIdx < 0) return Theme.t(lang, "Yok", "None")
    var label = "#" + (colIdx + 1)
    if (previewData && previewData.raw && previewData.raw.length > 0) {
      var firstRow = previewData.raw[0]
      if (firstRow && colIdx < firstRow.length && firstRow[colIdx]) {
        var sample = String(firstRow[colIdx]).trim()
        if (sample.length > 14) sample = sample.slice(0, 13) + "…"
        label += " (" + sample + ")"
      }
    }
    return label
  }

  function runConfirmImport() {
    if (!service || !previewPath) return
    var targetName = String(importListName || "").trim()
    service.confirmImport(previewPath, targetName, importCols, function(res) {
      root.previewData = null
      root.previewPath = ""
      if (res && res.ok) {
        root.importFeedback = Theme.t(root.lang, "Aktarıldı: ", "Imported ")
          + res.listName + " (+" + res.added + ")"
      } else if (res && res.error) {
        root.importFeedback = String(res.error)
      }
    })
  }

  function openListInspector(item) {
    if (!service || !item || !item.name) return
    inspectedListName = String(item.name)
    inspectedListSource = item.hasSource ? String(item.source || "") : ""
    inspectedWords = []
    service.loadListWords(inspectedListName, function(wordsArr) {
      root.inspectedWords = wordsArr || []
    })
  }

  // =========================================================================
  // 1) ANA LİSTELER GÖRÜNÜMÜ
  // =========================================================================
  Column {
    visible: root.previewData === null && root.inspectedListName === ""
    anchors.fill: parent
    anchors.margins: 34
    spacing: 18

    // Üst başlık + eylem düğmeleri
    Item {
      id: listHeaderBar
      width: parent.width
      height: Math.max(44, listHeaderCol.implicitHeight)

      Column {
        id: listHeaderCol
        anchors.left: parent.left
        anchors.right: listHeaderActions.left
        anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3

        Text {
          width: parent.width
          elide: Text.ElideRight
          text: Theme.t(root.lang, "Listeler", "Lists & Decks")
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
            "Aktif listelerden soru çekilir; CSV, TSV veya numaralı tablo PDF aktarabilirsin.",
            "Questions are drawn from enabled decks; import CSV, TSV, or numbered PDF tables."
          )
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.muted || "#a89984"
        }
      }

      Row {
        id: listHeaderActions
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Rectangle {
          width: starterBtnTxt.implicitWidth + 22
          height: 34
          radius: 7
          color: starterBtnArea.containsMouse
            ? (root.tokens.raised || "#504945")
            : (root.tokens.surface || "#32302f")
          border.width: 1
          border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

          Text {
            id: starterBtnTxt
            anchors.centerIn: parent
            text: Theme.t(root.lang, "Başlangıç destesi", "Load starter deck")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.ink || "#ebdbb2"
          }

          MouseArea {
            id: starterBtnArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              if (!root.service) return
              root.service.loadStarterDeck(function(res) {
                if (res && res.ok) {
                  root.importFeedback = Theme.t(root.lang, "Başlangıç destesi hazır (+", "Starter deck ready (+")
                    + res.added + ")"
                }
              })
            }
          }
        }

        Rectangle {
          width: impMainTxt.implicitWidth + 24
          height: 34
          radius: 7
          color: impMainArea.containsMouse
            ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
            : (root.tokens.primaryBg || "#fe8019")

          Text {
            id: impMainTxt
            anchors.centerIn: parent
            text: Theme.t(root.lang, "Dosya aktar…", "Import file…")
            font.family: root.fontFamily
            font.pixelSize: 12
            font.weight: Font.DemiBold
            color: root.tokens.primaryInk || "#1d2021"
          }

          MouseArea {
            id: impMainArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.startImportPicker()
          }
        }
      }
    }

    Text {
      visible: root.importFeedback.length > 0
      text: root.importFeedback
      font.family: root.fontFamily
      font.pixelSize: 12
      color: root.tokens.accent || "#fe8019"
    }

    Rectangle {
      width: parent.width
      height: 1
      color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
    }

    // Boş durum
    Column {
      visible: root.lists.length === 0
      width: parent.width
      topPadding: 36
      spacing: 8

      Text {
        text: Theme.t(root.lang, "Henüz hiç liste yok.", "No decks imported yet.")
        font.family: root.fontFamily
        font.pixelSize: 15
        font.weight: Font.Medium
        color: root.tokens.secondary || "#d5c4a1"
      }

      Text {
        width: parent.width
        wrapMode: Text.WordWrap
        text: Theme.t(
          root.lang,
          "30 kelimelik başlangıç destesiyle hemen deneyebilir veya kendi CSV/PDF kelime listeni içeri aktarabilirsin.",
          "Try the built-in 30-word academic starter deck or import any CSV, TSV, or numbered PDF vocabulary sheet."
        )
        font.family: root.fontFamily
        font.pixelSize: 13
        color: root.tokens.muted || "#a89984"
      }
    }

    // Liste satırları
    ListView {
      id: deckListView
      visible: root.lists.length > 0
      width: parent.width
      height: Math.max(80, parent.height - listHeaderBar.height - (root.importFeedback.length > 0 ? 72 : 42))
      clip: true
      spacing: 6
      model: root.lists

      delegate: Rectangle {
        width: deckListView.width
        height: 48
        radius: 8
        color: deckRowArea.containsMouse
          ? (root.tokens.surface2 || "#3c3836")
          : (root.tokens.surface || "#32302f")
        border.width: 1
        border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)

        MouseArea {
          id: deckRowArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.openListInspector(modelData)
        }

        // Aç / Kapat anahtarı
        Rectangle {
          id: toggleTrack
          anchors.left: parent.left
          anchors.leftMargin: 14
          anchors.verticalCenter: parent.verticalCenter
          width: 36
          height: 20
          radius: 10
          color: modelData.enabled
            ? (root.tokens.accent || "#fe8019")
            : (root.tokens.raised || "#504945")

          Rectangle {
            x: modelData.enabled ? 18 : 2
            anchors.verticalCenter: parent.verticalCenter
            width: 16
            height: 16
            radius: 8
            color: modelData.enabled
              ? (root.tokens.primaryInk || "#1d2021")
              : (root.tokens.muted || "#a89984")
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              if (root.service) {
                root.service.setListEnabled(String(modelData.name), !modelData.enabled)
              }
            }
          }
        }

        // Deste adı
        Text {
          anchors.left: toggleTrack.right
          anchors.leftMargin: 14
          anchors.verticalCenter: parent.verticalCenter
          width: parent.width - 260
          elide: Text.ElideRight
          text: String(modelData.name || "")
          font.family: root.fontFamily
          font.pixelSize: 14
          font.weight: Font.Medium
          color: modelData.enabled
            ? (root.tokens.ink || "#ebdbb2")
            : (root.tokens.muted || "#a89984")
        }

        Row {
          anchors.right: parent.right
          anchors.rightMargin: 14
          anchors.verticalCenter: parent.verticalCenter
          spacing: 12

          Rectangle {
            visible: !!modelData.hasSource
            width: srcOpenTxt.implicitWidth + 16
            height: 24
            radius: 5
            color: srcOpenArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : "transparent"
            border.width: 1
            border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16)

            Text {
              id: srcOpenTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Kaynağı aç", "Open source")
              font.family: root.fontFamily
              font.pixelSize: 11
              color: root.tokens.secondary || "#d5c4a1"
            }

            MouseArea {
              id: srcOpenArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service && modelData.source) {
                  root.service.openSourceFile(String(modelData.source))
                }
              }
            }
          }

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: String(modelData.count || 0) + " " + Theme.t(root.lang, "kelime →", "words →")
            font.family: "Monospace"
            font.pixelSize: 12
            color: root.tokens.muted || "#a89984"
          }
        }
      }
    }
  }

  // =========================================================================
  // 2) SEÇİLİ DESTE KELİME TABLOSU İNCELEYİCİSİ
  // =========================================================================
  Column {
    visible: root.previewData === null && root.inspectedListName !== ""
    anchors.fill: parent
    anchors.margins: 34
    spacing: 14

    Item {
      width: parent.width
      height: 36

      Rectangle {
        id: backListBtn
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: backListTxt.implicitWidth + 18
        height: 30
        radius: 7
        color: backListArea.containsMouse
          ? (root.tokens.raised || "#504945")
          : (root.tokens.surface || "#32302f")

        Text {
          id: backListTxt
          anchors.centerIn: parent
          text: Theme.t(root.lang, "← Listeler", "← Back")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.ink || "#ebdbb2"
        }

        MouseArea {
          id: backListArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.dismissOverlay()
        }
      }

      Text {
        anchors.left: backListBtn.right
        anchors.leftMargin: 12
        anchors.right: inspSrcBtn.visible ? inspSrcBtn.left : parent.right
        anchors.rightMargin: inspSrcBtn.visible ? 12 : 0
        anchors.verticalCenter: parent.verticalCenter
        elide: Text.ElideRight
        text: root.inspectedListName + " (" + root.inspectedWords.length + ")"
        font.family: root.fontFamily
        font.pixelSize: 18
        font.weight: Font.DemiBold
        color: root.tokens.ink || "#ebdbb2"
      }

      Rectangle {
        id: inspSrcBtn
        visible: root.inspectedListSource.length > 0
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: inspSrcTxt.implicitWidth + 20
        height: 30
        radius: 7
        color: inspSrcArea.containsMouse
          ? (root.tokens.raised || "#504945")
          : (root.tokens.surface || "#32302f")
        border.width: 1
        border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

        Text {
          id: inspSrcTxt
          anchors.centerIn: parent
          text: Theme.t(root.lang, "Kaynak dosyayı aç", "Open source file")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.secondary || "#d5c4a1"
        }

        MouseArea {
          id: inspSrcArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            if (root.service) root.service.openSourceFile(root.inspectedListSource)
          }
        }
      }
    }

    // Tablo başlığı
    Rectangle {
      width: parent.width
      height: 28
      radius: 6
      color: root.tokens.surface || "#32302f"

      Text {
        x: 12
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(parent.width * 0.25)
        text: Theme.t(root.lang, "KELİME", "WORD")
        font.family: root.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        color: root.tokens.muted || "#a89984"
      }

      Text {
        x: 12 + Math.round(parent.width * 0.26)
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(parent.width * 0.54)
        text: Theme.t(root.lang, "ANLAM", "MEANING")
        font.family: root.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        color: root.tokens.muted || "#a89984"
      }

      Text {
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        text: Theme.t(root.lang, "DURUM", "STAGE")
        font.family: root.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        color: root.tokens.muted || "#a89984"
      }
    }

    ListView {
      id: inspectedListView
      width: parent.width
      height: parent.height - 96
      clip: true
      spacing: 2
      model: root.inspectedWords

      delegate: Rectangle {
        width: inspectedListView.width
        height: 36
        radius: 6
        color: iRowArea.containsMouse
          ? (root.tokens.surface || "#32302f")
          : "transparent"

        Text {
          x: 12
          anchors.verticalCenter: parent.verticalCenter
          width: Math.round(parent.width * 0.25)
          elide: Text.ElideRight
          text: String(modelData.word || "")
          font.family: root.fontFamily
          font.pixelSize: 13
          font.weight: Font.Medium
          color: root.tokens.ink || "#ebdbb2"
        }

        Text {
          x: 12 + Math.round(parent.width * 0.26)
          anchors.verticalCenter: parent.verticalCenter
          width: Math.round(parent.width * 0.54)
          elide: Text.ElideRight
          text: String(modelData.meaning || "")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.secondary || "#d5c4a1"
        }

        Text {
          anchors.right: parent.right
          anchors.rightMargin: 12
          anchors.verticalCenter: parent.verticalCenter
          text: Theme.boxLabel(modelData.box, root.lang)
          font.family: root.fontFamily
          font.pixelSize: 11
          color: root.tokens.muted || "#a89984"
        }

        MouseArea {
          id: iRowArea
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

  // =========================================================================
  // 3) İÇE AKTARMA ÖNİZLEME & CSV SÜTUN EŞLEME GÖRÜNÜMÜ
  // =========================================================================
  Column {
    visible: root.previewData !== null
    anchors.fill: parent
    anchors.margins: 30
    spacing: 12

    Text {
      text: Theme.t(root.lang, "Listeyi İçe Aktar", "Import Vocabulary Deck")
      font.family: root.fontFamily
      font.pixelSize: 20
      font.weight: Font.DemiBold
      color: root.tokens.ink || "#ebdbb2"
    }

    // Deste adı girişi + algılanan satır özeti
    Row {
      width: parent.width
      spacing: 14

      Column {
        width: Math.round(parent.width * 0.52)
        spacing: 4

        Text {
          text: Theme.t(root.lang, "Liste adı", "Deck name")
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
          border.color: importNameInput.activeFocus
            ? (root.tokens.accent || "#fe8019")
            : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.16))

          TextInput {
            id: importNameInput
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            text: root.importListName
            onTextChanged: root.importListName = text
            font.family: root.fontFamily
            font.pixelSize: 13
            color: root.tokens.ink || "#ebdbb2"
            Keys.onReturnPressed: root.runConfirmImport()
          }
        }
      }

      Column {
        width: parent.width - Math.round(parent.width * 0.52) - 14
        spacing: 4

        Text {
          text: Theme.t(root.lang, "Kaynak", "Detected format")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.secondary || "#d5c4a1"
        }

        Text {
          width: parent.width
          elide: Text.ElideRight
          text: {
            if (!root.previewData) return ""
            var fmt = String(root.previewData.kind || "csv").toUpperCase()
            var tot = Number(root.previewData.total) || 0
            return fmt + " · " + tot + " " + Theme.t(root.lang, "satır bulundu", "rows parsed")
          }
          font.family: root.fontFamily
          font.pixelSize: 13
          font.weight: Font.Medium
          color: root.tokens.accent || "#fe8019"
        }
      }
    }

    // CSV 4 sütun eşleme seçicisi (PDF için otomatik tablo ayrıştırıcı kullanılır)
    Column {
      visible: !!(root.previewData && root.previewData.kind === "csv")
      width: parent.width
      spacing: 6

      Text {
        text: Theme.t(root.lang, "CSV SÜTUN EŞLEMESİ (Tıklayarak değiştir)", "CSV COLUMN MAPPING (Click to cycle column)")
        font.family: root.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.6
        color: root.tokens.muted || "#a89984"
      }

      Row {
        width: parent.width
        spacing: 8

        Repeater {
          model: [
            { slot: 0, label: Theme.t(root.lang, "Kelime", "Word") },
            { slot: 1, label: Theme.t(root.lang, "Anlam", "Meaning") },
            { slot: 2, label: Theme.t(root.lang, "Örnek", "Example") },
            { slot: 3, label: Theme.t(root.lang, "Çeviri", "Translation") }
          ]
          delegate: Rectangle {
            width: Math.floor((parent.width - 24) / 4)
            height: 44
            radius: 7
            color: mapSlotArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Column {
              anchors.fill: parent
              anchors.margins: 6
              spacing: 2

              Text {
                text: modelData.label
                font.family: root.fontFamily
                font.pixelSize: 10
                color: root.tokens.muted || "#a89984"
              }

              Text {
                width: parent.width
                elide: Text.ElideRight
                text: root._colSampleLabel(Number(root.importCols[modelData.slot]))
                font.family: root.fontFamily
                font.pixelSize: 12
                font.weight: Font.Medium
                color: root.tokens.ink || "#ebdbb2"
              }
            }

            MouseArea {
              id: mapSlotArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              acceptedButtons: Qt.LeftButton | Qt.RightButton
              onClicked: function(mouse) {
                root.cycleColumn(modelData.slot, mouse.button === Qt.RightButton ? -1 : 1)
              }
            }
          }
        }
      }
    }

    // 10 satırlık önizleme tablosu
    Rectangle {
      width: parent.width
      height: parent.height - ((root.previewData && root.previewData.kind === "csv") ? 240 : 172)
      radius: 8
      color: root.tokens.surface || "#32302f"
      border.width: 1
      border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)
      clip: true

      ListView {
        id: previewRowsList
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        spacing: 4
        model: (root.previewData && root.previewData.rows) ? root.previewData.rows : []

        delegate: Rectangle {
          width: previewRowsList.width
          height: 36
          radius: 5
          color: index % 2 === 0
            ? Theme.withAlpha(root.tokens.ink || "#ffffff", 0.03)
            : "transparent"

          Text {
            x: 8
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(parent.width * 0.24)
            elide: Text.ElideRight
            text: String(modelData.word || "")
            font.family: root.fontFamily
            font.pixelSize: 12
            font.weight: Font.DemiBold
            color: root.tokens.ink || "#ebdbb2"
          }

          Text {
            x: 8 + Math.round(parent.width * 0.25)
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(parent.width * 0.34)
            elide: Text.ElideRight
            text: String(modelData.meaning || "")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.secondary || "#d5c4a1"
          }

          Text {
            x: 8 + Math.round(parent.width * 0.60)
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(40, parent.width - x - 8)
            elide: Text.ElideRight
            text: String(modelData.example || "")
            font.family: root.fontFamily
            font.pixelSize: 11
            color: root.tokens.muted || "#a89984"
          }
        }
      }
    }

    // Alt onay / iptal düğmeleri
    Flow {
      width: parent.width
      spacing: 10

      Rectangle {
        readonly property int totRows: root.previewData ? (Number(root.previewData.total) || 0) : 0
        width: confirmImpTxt.implicitWidth + 28
        height: 34
        radius: 7
        opacity: totRows > 0 ? 1.0 : 0.45
        color: confirmImpArea.containsMouse
          ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
          : (root.tokens.primaryBg || "#fe8019")

        Text {
          id: confirmImpTxt
          anchors.centerIn: parent
          text: Theme.t(root.lang, "İçe aktar (", "Import (") + parent.totRows + ")"
          font.family: root.fontFamily
          font.pixelSize: 13
          font.weight: Font.DemiBold
          color: root.tokens.primaryInk || "#1d2021"
        }

        MouseArea {
          id: confirmImpArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            if (parent.totRows > 0) root.runConfirmImport()
          }
        }
      }

      Rectangle {
        width: cancelImpTxt.implicitWidth + 24
        height: 34
        radius: 7
        color: cancelImpArea.containsMouse
          ? (root.tokens.raised || "#504945")
          : (root.tokens.surface || "#32302f")

        Text {
          id: cancelImpTxt
          anchors.centerIn: parent
          text: Theme.t(root.lang, "Vazgeç", "Cancel")
          font.family: root.fontFamily
          font.pixelSize: 13
          color: root.tokens.ink || "#ebdbb2"
        }

        MouseArea {
          id: cancelImpArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.dismissOverlay()
        }
      }
    }
  }
}
