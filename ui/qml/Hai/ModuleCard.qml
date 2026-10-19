// Cartão de um módulo no menu. Arrastar a grade cancela o toque (o
// AbstractButton só dispara clicked se o dedo for solto sobre o cartão).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: card

    property var module: ({})
    property bool hero: false
    readonly property bool available: !module.reason

    focusPolicy: Qt.TabFocus
    implicitWidth: hero ? 420 : 300
    implicitHeight: hero ? 260 : 200
    Accessible.name: module.title || ""
    Accessible.description: module.reason || module.summary || ""

    background: Rectangle {
        radius: 16
        color: card.down ? theme.pressed : theme.card
        border.width: card.visualFocus ? 3 : 1
        border.color: card.visualFocus ? theme.focusRing : theme.border
        Behavior on color { ColorAnimation { duration: 80 } }
    }

    contentItem: ColumnLayout {
        spacing: 6
        Image {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 10
            source: card.module.icon || ""
            sourceSize.width: card.hero ? 112 : 84
            sourceSize.height: card.hero ? 112 : 84
            opacity: card.available ? 1 : 0.45
        }
        Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: card.module.title || ""
            font.pixelSize: theme.body
            font.bold: true
            color: card.available ? theme.text : theme.muted
            wrapMode: Text.Wrap
        }
        Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            visible: text !== ""
            text: card.available ? (card.module.summary || "") : "⚠ " + card.module.shortReason
            font.pixelSize: theme.small
            color: card.available ? theme.muted : theme.errorFg
            wrapMode: Text.Wrap
        }
        Item { Layout.fillHeight: true }
    }
}
