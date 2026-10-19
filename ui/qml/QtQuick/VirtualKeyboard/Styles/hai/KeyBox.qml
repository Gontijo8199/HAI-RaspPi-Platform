// Fundo de uma tecla, com um rótulo opcional no centro.
import QtQuick
import "Palette.js" as Palette

Rectangle {
    property bool special: false
    property bool down: false
    property bool accent: false
    property real scaleHint: 1
    property alias label: caption.text
    property alias labelColor: caption.color
    property alias labelSize: caption.font.pixelSize

    anchors.fill: parent
    anchors.margins: Math.round(4 * scaleHint)
    radius: Math.round(8 * scaleHint)
    color: accent ? (down ? Palette.accentPressed : Palette.accent)
         : down ? Palette.pressed : special ? Palette.specialKey : Palette.key
    border.width: 1
    border.color: Palette.border

    Text {
        id: caption
        anchors.centerIn: parent
        color: parent.accent ? "#ffffff" : Palette.text
        font.pixelSize: Math.round(20 * parent.scaleHint)
        font.weight: Font.DemiBold
    }
}
