// Cabeçalho de módulo: "← Menu", título e ações à direita (filhos do cabeçalho).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: header

    property alias title: titleLabel.text
    default property alias actions: tail.data
    signal back()

    spacing: 12

    HaiButton {
        objectName: "backButton"
        text: "← Menu"
        kind: "ghost"
        onClicked: header.back()
    }
    Label {
        id: titleLabel
        Layout.fillWidth: true
        font.pixelSize: theme.title
        font.bold: true
        color: theme.text
        elide: Text.ElideRight
    }
    Row {
        id: tail
        spacing: 8
    }
}
