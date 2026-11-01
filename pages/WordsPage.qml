import QtQuick
import qs.Commons
import "../Theme.js" as Theme

// Kelimeler sekmesi: solda arama, filtre yongaları (All | Custom | Hidden + liste seçici)
// ve son 5 cevap noktalı kelime listesi; sağda seçili kelimenin detayı veya Ekle/Düzenle formu.
Item {
  id: root

  property var service: null
  property string fontFamily: Style.font.family
  property string formMode: "" // "" | "add" | "edit"
  property bool listDropdownOpen: false

  // Form alanları
  property string formWord: ""
  property string formMeaning: ""
  property string formExample: ""
  property string formTranslation: ""
  property string formListName: "Custom"

  readonly property bool isEditingText: searchInput.activeFocus
    || fWordInput.activeFocus
    || fMeaningInput.activeFocus
    || fExampleInput.activeFocus
    || fTransInput.activeFocus
    || fListInput.activeFocus

  function releaseTextFocus() {
    if (!isEditingText) return false
    searchInput.focus = false
    fWordInput.focus = false
    fMeaningInput.focus = false
    fExampleInput.focus = false
    fTransInput.focus = false
    fListInput.focus = false
    return true
  }

  // Toplu seçim: id -> true. Silme iki adımlıdır (confirmDelete), Esc önce onayı sonra seçimi kapatır.
  property var selectedIds: ({})
  property bool confirmDelete: false
  readonly property int selCount: Object.keys(selectedIds).length
  readonly property bool allSelected: words.length > 0 && selCount === words.length

  function toggleSel(wordId) {
    var next = Object.assign({}, selectedIds)
    if (next[wordId]) delete next[wordId]
    else next[wordId] = true
    selectedIds = next
    confirmDelete = false
  }

  function clearSel() {
    selectedIds = ({})
    confirmDelete = false
  }

  function selectAllVisible() {
    var next = {}
    for (var i = 0; i < words.length; i++) next[words[i].id] = true
    selectedIds = next
    confirmDelete = false
  }

  function selectedList() {
    return Object.keys(selectedIds).map(function(k) { return Number(k) })
  }

  // Liste değişince (filtre, arama, silme) artık görünmeyen seçimleri bırak
  onWordsChanged: {
    var keep = {}
    for (var i = 0; i < words.length; i++) if (selectedIds[words[i].id]) keep[words[i].id] = true
    if (Object.keys(keep).length !== selCount) selectedIds = keep
    if (Object.keys(keep).length === 0) confirmDelete = false
  }

  function dismissOverlay() {
    if (confirmDelete) {
      confirmDelete = false
      return true
    }
    if (selCount > 0) {
      clearSel()
      return true
    }
    if (listDropdownOpen) {
      listDropdownOpen = false
      return true
    }
    if (formMode !== "") {
      formMode = ""
      return true
    }
    return false
  }

  readonly property string lang: service ? service.lang : "en"
  readonly property var tokens: service ? service.tokens : ({})
  readonly property var words: service && service.wordsData ? service.wordsData : []
  readonly property var lists: service && service.listsData ? service.listsData : []
  readonly property var detail: service ? service.selectedWord : null
  readonly property string activeFilter: service ? service.wordsListFilter : ""

  // Düzenleme formu açıkken arka planda zenginleştirme tamamlanırsa yalnız boş alanları doldur
  Connections {
    target: root.service
    function onSelectedWordChanged() {
      if (root.formMode === "edit" && root.detail) {
        if (!root.formMeaning && root.detail.meaning) root.formMeaning = String(root.detail.meaning)
        if (!root.formExample && root.detail.example) root.formExample = String(root.detail.example)
        if (!root.formTranslation && root.detail.translation && root.formExample === String(root.detail.example || "")) {
          root.formTranslation = String(root.detail.translation)
        }
      }
    }
  }

  function selectWordById(wordId) {
    formMode = ""
    listDropdownOpen = false
    if (service) service.refreshSnapshot({ selectedWordId: Number(wordId) })
  }

  function openAddForm() {
    listDropdownOpen = false
    formMode = "add"
    formWord = ""
    formMeaning = ""
    formExample = ""
    formTranslation = ""
    formListName = (activeFilter && activeFilter.indexOf("__") !== 0)
      ? activeFilter
      : "Custom"
    Qt.callLater(function() { fWordInput.forceActiveFocus() })
  }

  function openEditForm() {
    if (!detail) return
    listDropdownOpen = false
    formMode = "edit"
    formWord = String(detail.word || "")
    formMeaning = String(detail.meaning || "")
    formExample = String(detail.example || "")
    formTranslation = String(detail.translation || "")
    formListName = String(detail.listName || "Custom")
    Qt.callLater(function() { fMeaningInput.forceActiveFocus() })
  }

  function submitForm() {
    if (!service) return
    var w = String(formWord || "").trim()
    if (!w) return
    if (formMode === "add") {
      service.addManualWord({
        word: w,
        meaning: String(formMeaning || "").trim(),
        example: String(formExample || "").trim(),
        translation: String(formTranslation || "").trim(),
        listName: String(formListName || "Custom").trim() || "Custom"
      }, function() {
        root.formMode = ""
      })
    } else if (formMode === "edit" && detail) {
      service.updateWord({
        wordId: detail.id,
        word: w,
        meaning: String(formMeaning || "").trim(),
        example: String(formExample || "").trim(),
        translation: String(formTranslation || "").trim(),
        listName: String(formListName || "Custom").trim() || "Custom"
      }, function() {
        root.formMode = ""
      })
    }
  }

  Row {
    anchors.fill: parent

    // --- SOL LİSTE SÜTUNU (286px) ---
    Rectangle {
      width: 286
      height: parent.height
      color: "transparent"

      Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: root.tokens.line || Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        // Arama + "+ Ekle"
        Row {
          width: parent.width
          spacing: 6

          Rectangle {
            width: parent.width - addWordBtn.width - 6
            height: 32
            radius: 7
            color: root.tokens.surface || "#32302f"
            border.width: 1
            border.color: searchInput.activeFocus
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.line || Qt.rgba(1, 1, 1, 0.10))

            Text {
              visible: searchInput.text.length === 0
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.leftMargin: 9
              anchors.rightMargin: 9
              anchors.verticalCenter: parent.verticalCenter
              elide: Text.ElideRight
              text: Theme.t(root.lang, "Kelime veya anlam ara…", "Search words…")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.muted || "#a89984"
            }

            TextInput {
              id: searchInput
              anchors.fill: parent
              anchors.leftMargin: 9
              anchors.rightMargin: 9
              verticalAlignment: TextInput.AlignVCenter
              clip: true
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
              selectionColor: root.tokens.accent || "#fe8019"
              selectedTextColor: root.tokens.primaryInk || "#1d2021"
              onTextChanged: {
                root.formMode = ""
                searchDebounce.restart()
              }
            }
          }

          Rectangle {
            id: addWordBtn
            width: Math.max(64, addWordBtnTxt.implicitWidth + 18)
            height: 32
            radius: 7
            color: addBtnArea.containsMouse
              ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
              : (root.tokens.primaryBg || "#fe8019")

            Text {
              id: addWordBtnTxt
              anchors.centerIn: parent
              text: Theme.t(root.lang, "+ Ekle", "+ Add")
              font.family: root.fontFamily
              font.pixelSize: 12
              font.weight: Font.DemiBold
              color: root.tokens.primaryInk || "#1d2021"
            }

            MouseArea {
              id: addBtnArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.openAddForm()
            }
          }
        }

        Timer {
          id: searchDebounce
          interval: 160
          repeat: false
          onTriggered: {
            if (root.service) root.service.refreshSnapshot({ query: searchInput.text })
          }
        }

        // Filtre yongaları: All | Custom | Hidden + Liste seçici
        Flow {
          id: filterChipsFlow
          width: parent.width
          spacing: 5

          Repeater {
            model: [
              { key: "", label: Theme.t(root.lang, "Hepsi", "All") },
              { key: "__custom__", label: Theme.t(root.lang, "Kendi", "Custom") },
              { key: "__hidden__", label: Theme.t(root.lang, "Gizli", "Hidden") },
              { key: "__learned__", label: Theme.t(root.lang, "Öğrendim", "Learned") }
            ]
            delegate: Rectangle {
              readonly property bool sel: root.activeFilter === modelData.key
              width: chipLbl.implicitWidth + 16
              height: 24
              radius: 6
              color: sel
                ? (root.tokens.raised || "#504945")
                : (chipArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
              border.width: 1
              border.color: sel
                ? (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.22))
                : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

              Text {
                id: chipLbl
                anchors.centerIn: parent
                text: modelData.label
                font.family: root.fontFamily
                font.pixelSize: 11
                font.weight: sel ? Font.DemiBold : Font.Normal
                color: sel ? (root.tokens.ink || "#ebdbb2") : (root.tokens.secondary || "#d5c4a1")
              }

              MouseArea {
                id: chipArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  root.formMode = ""
                  root.listDropdownOpen = false
                  if (root.service) root.service.refreshSnapshot({ listFilter: modelData.key, selectedWordId: 0 })
                }
              }
            }
          }

          Rectangle {
            readonly property bool customListActive: root.activeFilter !== ""
              && root.activeFilter.indexOf("__") !== 0
            width: Math.max(66, Math.min(106, deckChipTxt.implicitWidth + 16))
            height: 24
            radius: 6
            color: customListActive
              ? (root.tokens.raised || "#504945")
              : (deckChipArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")
            border.width: 1
            border.color: customListActive
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.line || Qt.rgba(1, 1, 1, 0.08))

            Text {
              id: deckChipTxt
              anchors.centerIn: parent
              width: parent.width - 12
              horizontalAlignment: Text.AlignHCenter
              elide: Text.ElideRight
              text: parent.customListActive
                ? (root.activeFilter + " ▾")
                : Theme.t(root.lang, "Liste ▾", "Deck ▾")
              font.family: root.fontFamily
              font.pixelSize: 11
              color: parent.customListActive
                ? (root.tokens.ink || "#ebdbb2")
                : (root.tokens.secondary || "#d5c4a1")
            }

            MouseArea {
              id: deckChipArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.listDropdownOpen = !root.listDropdownOpen
            }
          }
        }

        // Açılır liste seçici
        Rectangle {
          visible: root.listDropdownOpen && root.lists.length > 0
          width: parent.width
          height: visible ? Math.min(144, deckDropCol.implicitHeight + 10) : 0
          radius: 7
          color: root.tokens.surface2 || "#3c3836"
          border.width: 1
          border.color: root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.18)
          clip: true

          Flickable {
            anchors.fill: parent
            anchors.margins: 5
            contentHeight: deckDropCol.implicitHeight

            Column {
              id: deckDropCol
              width: parent.width
              spacing: 2

              Repeater {
                model: root.lists
                delegate: Rectangle {
                  width: deckDropCol.width
                  height: 26
                  radius: 5
                  color: ddArea.containsMouse
                    ? (root.tokens.raised || "#504945")
                    : "transparent"

                  Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.name || "")
                    font.family: root.fontFamily
                    font.pixelSize: 12
                    color: root.tokens.ink || "#ebdbb2"
                  }

                  Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.count || 0)
                    font.family: "Monospace"
                    font.pixelSize: 11
                    color: root.tokens.muted || "#a89984"
                  }

                  MouseArea {
                    id: ddArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.listDropdownOpen = false
                      root.formMode = ""
                      if (root.service) {
                        root.service.refreshSnapshot({ listFilter: String(modelData.name), selectedWordId: 0 })
                      }
                    }
                  }
                }
              }
            }
          }
        }

        // Toplu seçim çubuğu: tümünü seç kutusu + sayı; seçim varken Öğrendim / Sil / ✕
        Item {
          id: bulkBar
          width: parent.width
          height: 26

          Item {
            id: allBox
            anchors.left: parent.left
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            width: 26
            height: 26
            visible: root.words.length > 0

            Rectangle {
              anchors.centerIn: parent
              width: 14
              height: 14
              radius: 3
              color: root.allSelected ? (root.tokens.accent || "#fe8019") : "transparent"
              border.width: 1
              border.color: (root.selCount > 0) ? (root.tokens.accent || "#fe8019") : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.3))

              Text {
                anchors.centerIn: parent
                visible: root.selCount > 0
                text: root.allSelected ? "✓" : "–"
                font.pixelSize: 10
                font.weight: Font.Bold
                color: root.allSelected ? (root.tokens.primaryInk || "#1d2021") : (root.tokens.accent || "#fe8019")
              }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.allSelected ? root.clearSel() : root.selectAllVisible()
            }
          }

          Text {
            anchors.left: allBox.visible ? allBox.right : parent.left
            anchors.leftMargin: allBox.visible ? 2 : 0
            anchors.verticalCenter: parent.verticalCenter
            text: root.confirmDelete
              ? (root.selCount + Theme.t(root.lang, " silinsin mi?", " delete?"))
              : root.selCount > 0
              ? (root.selCount + Theme.t(root.lang, " seçili", " selected"))
              : (root.words.length + " " + Theme.t(root.lang, "kelime", root.words.length === 1 ? "word" : "words"))
            font.family: root.fontFamily
            font.pixelSize: 11
            font.weight: root.selCount > 0 ? Font.DemiBold : Font.Normal
            color: root.selCount > 0 ? (root.tokens.ink || "#ebdbb2") : (root.tokens.muted || "#a89984")
          }

          Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            visible: root.selCount > 0

            Repeater {
              model: root.confirmDelete
                ? [
                    { act: "delete", label: Theme.t(root.lang, "Sil", "Delete"), danger: true },
                    { act: "cancel", label: Theme.t(root.lang, "Vazgeç", "Cancel"), danger: false }
                  ]
                : [
                    { act: "learned", label: root.activeFilter === "__learned__"
                        ? Theme.t(root.lang, "Geri al", "Restore")
                        : Theme.t(root.lang, "Öğrendim", "Learned"), danger: false },
                    { act: "ask-delete", label: Theme.t(root.lang, "Sil", "Delete"), danger: true },
                    { act: "clear", label: "✕", danger: false }
                  ]
              delegate: Rectangle {
                width: bulkLbl.implicitWidth + 14
                height: 22
                radius: 5
                color: bulkArea.containsMouse
                  ? (modelData.danger ? Theme.withAlpha(root.tokens.danger || "#fb4934", 0.22) : (root.tokens.raised || "#504945"))
                  : (modelData.danger && root.confirmDelete ? Theme.withAlpha(root.tokens.danger || "#fb4934", 0.14) : (root.tokens.surface || "#32302f"))
                border.width: 1
                border.color: modelData.danger
                  ? Theme.withAlpha(root.tokens.danger || "#fb4934", 0.5)
                  : (root.tokens.line || Qt.rgba(1, 1, 1, 0.10))

                Text {
                  id: bulkLbl
                  anchors.centerIn: parent
                  text: modelData.label
                  font.family: root.fontFamily
                  font.pixelSize: 11
                  color: modelData.danger ? (root.tokens.danger || "#fb4934") : (root.tokens.ink || "#ebdbb2")
                }

                MouseArea {
                  id: bulkArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (!root.service) return
                    var ids = root.selectedList()
                    if (modelData.act === "learned") {
                      root.service.setWordsLearned(ids, root.activeFilter !== "__learned__", null)
                      root.clearSel()
                    } else if (modelData.act === "ask-delete") {
                      root.confirmDelete = true
                    } else if (modelData.act === "delete") {
                      if (root.formMode === "edit" && root.detail && ids.indexOf(Number(root.detail.id)) >= 0) root.formMode = ""
                      root.service.deleteWords(ids, null)
                      root.clearSel()
                    } else if (modelData.act === "cancel") {
                      root.confirmDelete = false
                    } else {
                      root.clearSel()
                    }
                  }
                }
              }
            }
          }
        }

        // Kelime listesi
        ListView {
          id: wordsListView
          width: parent.width
          height: Math.max(60, parent.height - 106 - filterChipsFlow.implicitHeight - (root.listDropdownOpen && root.lists.length > 0 ? Math.min(144, deckDropCol.implicitHeight + 20) : 0))
          clip: true
          spacing: 2
          model: root.words

          delegate: Rectangle {
            id: wordRow
            readonly property bool selected: !!(root.detail && Number(root.detail.id) === Number(modelData.id) && root.formMode !== "add")
            width: wordsListView.width
            height: 44
            radius: 7
            color: selected
              ? (root.tokens.raised || "#504945")
              : (rowArea.containsMouse ? (root.tokens.surface || "#32302f") : "transparent")

            readonly property bool checked: !!root.selectedIds[modelData.id]

            Column {
              anchors.left: parent.left
              anchors.leftMargin: 32
              anchors.right: dotsRow.left
              anchors.rightMargin: 8
              anchors.verticalCenter: parent.verticalCenter
              spacing: 2

              Text {
                width: parent.width
                elide: Text.ElideRight
                text: String(modelData.word || "")
                font.family: root.fontFamily
                font.pixelSize: 13
                font.weight: selected ? Font.DemiBold : Font.Medium
                color: root.tokens.ink || "#ebdbb2"
              }

              Text {
                width: parent.width
                elide: Text.ElideRight
                text: modelData.meaning
                  ? String(modelData.meaning)
                  : (modelData.enriched
                    ? Theme.t(root.lang, "anlam bulunamadı · Düzenle ile ekle", "no meaning found · add it with Edit")
                    : Theme.t(root.lang, "anlam aranıyor…", "enriching…"))
                font.family: root.fontFamily
                font.pixelSize: 11
                font.italic: !modelData.meaning
                color: root.tokens.muted || "#a89984"
              }
            }

            // Son 5 cevap noktası
            Row {
              id: dotsRow
              anchors.right: parent.right
              anchors.rightMargin: 10
              anchors.verticalCenter: parent.verticalCenter
              spacing: 3

              Repeater {
                model: modelData.last5 ? modelData.last5 : []
                delegate: Rectangle {
                  width: 6
                  height: 6
                  radius: 3
                  color: modelData === "correct"
                    ? (root.tokens.ok || "#b8bb26")
                    : (root.tokens.danger || "#fb4934")
                }
              }
            }

            MouseArea {
              id: rowArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: function(mouse) {
                if (mouse.modifiers & Qt.ControlModifier) root.toggleSel(modelData.id)
                else root.selectWordById(modelData.id)
              }
            }

            // Seçim kutusu (satıra tıklamak ayrıntıyı açar; kutu ya da Ctrl+tık seçer)
            Item {
              anchors.left: parent.left
              anchors.leftMargin: 4
              anchors.verticalCenter: parent.verticalCenter
              width: 26
              height: 26

              Rectangle {
                anchors.centerIn: parent
                width: 14
                height: 14
                radius: 3
                color: wordRow.checked ? (root.tokens.accent || "#fe8019") : "transparent"
                border.width: 1
                border.color: wordRow.checked
                  ? (root.tokens.accent || "#fe8019")
                  : (boxArea.containsMouse ? (root.tokens.ink || "#ebdbb2") : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.3)))

                Text {
                  anchors.centerIn: parent
                  visible: wordRow.checked
                  text: "✓"
                  font.pixelSize: 10
                  font.weight: Font.Bold
                  color: root.tokens.primaryInk || "#1d2021"
                }
              }

              MouseArea {
                id: boxArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.toggleSel(modelData.id)
              }
            }
          }
        }
      }
    }

    // --- SAĞ DETAY VEYA EKLE/DÜZENLE SÜTUNU ---
    Item {
      width: parent.width - 286
      height: parent.height

      // 1) EKLE / DÜZENLE FORMU
      Column {
        visible: root.formMode !== ""
        anchors.fill: parent
        anchors.margins: 30
        spacing: 14

        Text {
          text: root.formMode === "add"
            ? Theme.t(root.lang, "Yeni kelime ekle", "Add new word")
            : Theme.t(root.lang, "Kelimeyi düzenle", "Edit word")
          font.family: root.fontFamily
          font.pixelSize: 20
          font.weight: Font.DemiBold
          color: root.tokens.ink || "#ebdbb2"
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: Theme.t(
            root.lang,
            "Anlam ve örnek cümleyi boş bırakırsan ücretsiz sözlük (ve açıksa AI) arka planda doldurur.",
            "Leave meaning and example blank to let Free Dictionary (and optional AI) fill them automatically."
          )
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.muted || "#a89984"
        }

        // Kelime
        Column {
          width: parent.width
          spacing: 4

          Text {
            width: parent.width
            elide: Text.ElideRight
            text: Theme.t(root.lang, "Kelime / İfade", "Word / Phrase")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.secondary || "#d5c4a1"
          }

          Rectangle {
            width: parent.width
            height: 34
            radius: 7
            color: root.tokens.surface || "#32302f"
            border.width: 1
            border.color: fWordInput.activeFocus
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

            TextInput {
              id: fWordInput
              anchors.fill: parent
              anchors.leftMargin: 10
              anchors.rightMargin: 10
              verticalAlignment: TextInput.AlignVCenter
              clip: true
              text: root.formWord
              onTextChanged: root.formWord = text
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.ink || "#ebdbb2"
              Keys.onReturnPressed: root.submitForm()
            }
          }
        }

        // Anlam
        Column {
          width: parent.width
          spacing: 4

          Text {
            width: parent.width
            elide: Text.ElideRight
            text: Theme.t(root.lang, "Anlam (virgülle ayrılmış)", "Meaning (comma-separated, optional)")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.secondary || "#d5c4a1"
          }

          Rectangle {
            width: parent.width
            height: 34
            radius: 7
            color: root.tokens.surface || "#32302f"
            border.width: 1
            border.color: fMeaningInput.activeFocus
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

            TextInput {
              id: fMeaningInput
              anchors.fill: parent
              anchors.leftMargin: 10
              anchors.rightMargin: 10
              verticalAlignment: TextInput.AlignVCenter
              clip: true
              text: root.formMeaning
              onTextChanged: root.formMeaning = text
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.ink || "#ebdbb2"
              Keys.onReturnPressed: root.submitForm()
            }
          }
        }

        // Örnek cümle
        Column {
          width: parent.width
          spacing: 4

          Text {
            width: parent.width
            elide: Text.ElideRight
            text: Theme.t(root.lang, "Örnek cümle (isteğe bağlı)", "Example sentence (optional)")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.secondary || "#d5c4a1"
          }

          Rectangle {
            width: parent.width
            height: 34
            radius: 7
            color: root.tokens.surface || "#32302f"
            border.width: 1
            border.color: fExampleInput.activeFocus
              ? (root.tokens.accent || "#fe8019")
              : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

            TextInput {
              id: fExampleInput
              anchors.fill: parent
              anchors.leftMargin: 10
              anchors.rightMargin: 10
              verticalAlignment: TextInput.AlignVCenter
              clip: true
              text: root.formExample
              onTextChanged: root.formExample = text
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.ink || "#ebdbb2"
            }
          }
        }

        // Çeviri + Liste yan yana
        Row {
          width: parent.width
          spacing: 12

          Column {
            width: Math.round((parent.width - 12) * 0.65)
            spacing: 4

            Text {
              width: parent.width
              elide: Text.ElideRight
              text: Theme.t(root.lang, "Cümle çevirisi (isteğe bağlı)", "Sentence translation (optional)")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Rectangle {
              width: parent.width
              height: 34
              radius: 7
              color: root.tokens.surface || "#32302f"
              border.width: 1
              border.color: fTransInput.activeFocus
                ? (root.tokens.accent || "#fe8019")
                : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

              TextInput {
                id: fTransInput
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                text: root.formTranslation
                onTextChanged: root.formTranslation = text
                font.family: root.fontFamily
                font.pixelSize: 13
                color: root.tokens.ink || "#ebdbb2"
              }
            }
          }

          Column {
            width: parent.width - 12 - Math.round((parent.width - 12) * 0.65)
            spacing: 4

            Text {
              width: parent.width
              elide: Text.ElideRight
              text: Theme.t(root.lang, "Liste", "Deck")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            Rectangle {
              width: parent.width
              height: 34
              radius: 7
              color: root.tokens.surface || "#32302f"
              border.width: 1
              border.color: fListInput.activeFocus
                ? (root.tokens.accent || "#fe8019")
                : (root.tokens.lineStrong || Qt.rgba(1, 1, 1, 0.14))

              TextInput {
                id: fListInput
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                text: root.formListName
                onTextChanged: root.formListName = text
                font.family: root.fontFamily
                font.pixelSize: 13
                color: root.tokens.ink || "#ebdbb2"
              }
            }
          }
        }

        Flow {
          width: parent.width
          spacing: 10

          Rectangle {
            width: saveFormLbl.implicitWidth + 28
            height: 34
            radius: 7
            color: saveFormArea.containsMouse
              ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
              : (root.tokens.primaryBg || "#fe8019")

            Text {
              id: saveFormLbl
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Kaydet", "Save")
              font.family: root.fontFamily
              font.pixelSize: 13
              font.weight: Font.DemiBold
              color: root.tokens.primaryInk || "#1d2021"
            }

            MouseArea {
              id: saveFormArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.submitForm()
            }
          }

          Rectangle {
            width: cancelFormLbl.implicitWidth + 24
            height: 34
            radius: 7
            color: cancelFormArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")

            Text {
              id: cancelFormLbl
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Vazgeç", "Cancel")
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: cancelFormArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.formMode = ""
            }
          }
        }
      }

      // 2) SEÇİLİ KELİME DETAYI
      Column {
        visible: root.formMode === "" && root.detail !== null
        anchors.fill: parent
        anchors.margins: 32
        spacing: 18

        // Üst etiketler: liste adı + sözcük türü + kutu durumu
        Flow {
          width: parent.width
          spacing: 8

          Rectangle {
            height: 22
            width: Math.min(parent.width, dListTxt.implicitWidth + 14)
            radius: 5
            color: root.tokens.surface || "#32302f"

            Text {
              id: dListTxt
              anchors.centerIn: parent
              width: Math.min(implicitWidth, parent.width - 12)
              elide: Text.ElideRight
              text: root.detail ? String(root.detail.listName || "Custom") : ""
              font.family: root.fontFamily
              font.pixelSize: 11
              color: root.tokens.secondary || "#d5c4a1"
            }
          }

          Rectangle {
            visible: !!(root.detail && root.detail.pos && root.detail.pos !== "other")
            height: 22
            width: dPosTxt.implicitWidth + 14
            radius: 5
            color: root.tokens.surface || "#32302f"

            Text {
              id: dPosTxt
              anchors.centerIn: parent
              text: root.detail ? String(root.detail.pos || "") : ""
              font.family: root.fontFamily
              font.pixelSize: 11
              color: root.tokens.muted || "#a89984"
            }
          }

          Text {
            topPadding: 3
            text: root.detail ? Theme.boxLabel(root.detail.box, root.lang) : ""
            font.family: root.fontFamily
            font.pixelSize: 11
            color: root.tokens.muted || "#a89984"
          }
        }

        Column {
          width: parent.width
          spacing: 6

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: root.detail ? String(root.detail.word || "") : ""
            font.family: root.fontFamily
            font.pixelSize: 30
            font.weight: Font.Bold
            color: root.tokens.ink || "#ebdbb2"
          }

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: {
              if (!root.detail) return ""
              if (root.detail.meaning) return String(root.detail.meaning)
              if (root.detail.enriched) return Theme.t(root.lang, "Anlam bulunamadı · Düzenle ile ekleyebilirsin", "No meaning found · add one with Edit")
              return Theme.t(root.lang, "Anlam sözlükten aranıyor…", "Looking up meaning in dictionary…")
            }
            font.family: root.fontFamily
            font.pixelSize: 16
            font.italic: !(root.detail && root.detail.meaning)
            color: root.tokens.secondary || "#d5c4a1"
          }
        }

        // Sol çizgili örnek cümle + italik çeviri
        Rectangle {
          visible: !!(root.detail && (root.detail.example || root.detail.translation))
          width: parent.width
          height: visible ? (exDetailCol.implicitHeight + 20) : 0
          radius: 7
          color: Theme.withAlpha(root.tokens.ink || "#ffffff", 0.04)

          Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 3
            radius: 2
            color: root.tokens.accent || "#fe8019"
          }

          Column {
            id: exDetailCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 14
            anchors.rightMargin: 12
            spacing: 5

            Text {
              visible: !!(root.detail && root.detail.example)
              width: parent.width
              wrapMode: Text.WordWrap
              textFormat: Text.RichText
              text: root.detail ? String(root.detail.exampleHtml || root.detail.example || "") : ""
              font.family: root.fontFamily
              font.pixelSize: 14
              color: root.tokens.ink || "#ebdbb2"
            }

            Text {
              visible: !!(root.detail && root.detail.translation)
              width: parent.width
              wrapMode: Text.WordWrap
              font.italic: true
              text: root.detail ? String(root.detail.translation || "") : ""
              font.family: root.fontFamily
              font.pixelSize: 13
              color: root.tokens.muted || "#a89984"
            }
          }
        }

        // Cevap geçmişi kareleri
        Column {
          width: parent.width
          spacing: 6

          Text {
            text: Theme.t(root.lang, "CEVAP GEÇMİŞİ", "ANSWER HISTORY")
            font.family: root.fontFamily
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.letterSpacing: 0.8
            color: root.tokens.muted || "#a89984"
          }

          Text {
            visible: !(root.detail && root.detail.history && root.detail.history.length > 0)
            text: Theme.t(root.lang, "Henüz sorulmadı.", "Not answered yet.")
            font.family: root.fontFamily
            font.pixelSize: 12
            color: root.tokens.muted || "#a89984"
          }

          Flow {
            width: parent.width
            spacing: 5

            Repeater {
              model: (root.detail && root.detail.history) ? root.detail.history : []
              delegate: Rectangle {
                width: 12
                height: 12
                radius: 3
                color: modelData === "correct"
                  ? (root.tokens.ok || "#b8bb26")
                  : (root.tokens.danger || "#fb4934")
              }
            }
          }
        }

        // Eylem düğmeleri: Şimdi sor · Düzenle · Gizle/Geri aç
        Flow {
          width: parent.width
          spacing: 8

          Rectangle {
            visible: !!(root.detail && root.detail.meaning)
            width: dAskLbl.implicitWidth + 24
            height: 32
            radius: 7
            color: dAskArea.containsMouse
              ? Theme.withAlpha(root.tokens.primaryBg || "#fe8019", 0.88)
              : (root.tokens.primaryBg || "#fe8019")

            Text {
              id: dAskLbl
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Şimdi sor", "Ask now")
              font.family: root.fontFamily
              font.pixelSize: 12
              font.weight: Font.DemiBold
              color: root.tokens.primaryInk || "#1d2021"
            }

            MouseArea {
              id: dAskArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service && root.detail) root.service.askNow(root.detail.id)
              }
            }
          }

          Rectangle {
            width: dEditLbl.implicitWidth + 22
            height: 32
            radius: 7
            color: dEditArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : (root.tokens.surface || "#32302f")
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: dEditLbl
              anchors.centerIn: parent
              text: Theme.t(root.lang, "Düzenle", "Edit")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.ink || "#ebdbb2"
            }

            MouseArea {
              id: dEditArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.openEditForm()
            }
          }

          Rectangle {
            width: dLearnLbl.implicitWidth + 22
            height: 32
            radius: 7
            color: dLearnArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : "transparent"
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: dLearnLbl
              anchors.centerIn: parent
              text: (root.detail && root.detail.learned)
                ? Theme.t(root.lang, "Tekrar sor", "Ask again")
                : Theme.t(root.lang, "Öğrendim", "Learned")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            MouseArea {
              id: dLearnArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service && root.detail) {
                  root.service.setWordsLearned([root.detail.id], !root.detail.learned, null)
                }
              }
            }
          }

          Rectangle {
            width: dHideLbl.implicitWidth + 22
            height: 32
            radius: 7
            color: dHideArea.containsMouse
              ? (root.tokens.raised || "#504945")
              : "transparent"
            border.width: 1
            border.color: root.tokens.line || Qt.rgba(1, 1, 1, 0.10)

            Text {
              id: dHideLbl
              anchors.centerIn: parent
              text: (root.detail && root.detail.hidden)
                ? Theme.t(root.lang, "Gizlemeyi kaldır", "Unhide")
                : Theme.t(root.lang, "Gizle", "Hide")
              font.family: root.fontFamily
              font.pixelSize: 12
              color: root.tokens.secondary || "#d5c4a1"
            }

            MouseArea {
              id: dHideArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service && root.detail) {
                  root.service.setWordHidden(root.detail.id, !root.detail.hidden)
                }
              }
            }
          }
        }
      }

      // 3) BOŞ DURUM
      Column {
        visible: root.formMode === "" && root.detail === null
        anchors.centerIn: parent
        spacing: 8

        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: Theme.t(root.lang, "Seçili kelime yok", "No word selected")
          font.family: root.fontFamily
          font.pixelSize: 15
          font.weight: Font.Medium
          color: root.tokens.secondary || "#d5c4a1"
        }

        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: Theme.t(root.lang, "+ Ekle ile yeni kelime ekleyebilirsin.", "Click + Add to add a word.")
          font.family: root.fontFamily
          font.pixelSize: 12
          color: root.tokens.muted || "#a89984"
        }
      }
    }
  }
}
