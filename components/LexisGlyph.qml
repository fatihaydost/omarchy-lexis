import QtQuick
import qs.Commons

// Tipografik marka işareti: barda kompakt "l.", panel başlığında isteğe bağlı "lexis."
Item {
  id: root

  property int pixelSize: 15
  property bool fullWord: false
  property color inkColor: "#ebdbb2"
  property color dotColor: "#fe8019"
  property string fontFamily: Style.font.family

  implicitWidth: markRow.implicitWidth
  implicitHeight: markRow.implicitHeight

  Row {
    id: markRow
    anchors.centerIn: parent
    spacing: 0

    Text {
      text: root.fullWord ? "lexis" : "l"
      font.family: root.fontFamily
      font.pixelSize: Math.max(10, Math.round(root.pixelSize))
      font.weight: Font.Bold
      renderType: Text.NativeRendering
      color: root.inkColor
    }

    Text {
      text: "."
      font.family: root.fontFamily
      font.pixelSize: Math.max(10, Math.round(root.pixelSize))
      font.weight: Font.Bold
      renderType: Text.NativeRendering
      color: root.dotColor
    }
  }
}
