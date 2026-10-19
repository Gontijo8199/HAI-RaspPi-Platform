// Confirmação modal: escurece a tela, Esc ou toque fora cancelam.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: dialog

    property string title: ""
    property string message: ""
    property string confirmLabel: "Confirmar"
    property string cancelLabel: "Cancelar"
    property string confirmKind: "danger"
    signal confirmed()

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(560, parent ? parent.width - 32 : 560)
    modal: true
    dim: true
    focus: true
    padding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: theme.shade }
    background: Rectangle { color: theme.card; radius: 14 }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90 } }

    contentItem: ColumnLayout {
        spacing: 12
        Label {
            Layout.fillWidth: true
            text: dialog.title
            font.pixelSize: theme.title
            font.bold: true
            color: theme.text
            wrapMode: Text.Wrap
        }
        Label {
            Layout.fillWidth: true
            text: dialog.message
            font.pixelSize: theme.body
            color: theme.muted
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.topMargin: 8
            spacing: 10
            Item { Layout.fillWidth: true }
            HaiButton {
                objectName: "dialogCancel"
                text: dialog.cancelLabel
                kind: "secondary"
                onClicked: dialog.close()
            }
            HaiButton {
                objectName: "dialogConfirm"
                text: dialog.confirmLabel
                kind: dialog.confirmKind
                onClicked: { dialog.close(); dialog.confirmed() }
            }
        }
    }
}
