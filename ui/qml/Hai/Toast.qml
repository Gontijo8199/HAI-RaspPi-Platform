// Aviso no fluxo da tela (não cobre o conteúdo). Erros ficam até serem
// dispensados; avisos informativos somem sozinhos (quem decide é o controller).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: toast

    property string kind: "info"
    property string message: ""
    property string actionLabel: ""
    signal action()
    signal dismissed()

    visible: message !== ""
    implicitHeight: visible ? row.implicitHeight + 12 : 0
    radius: 10
    color: kind === "error" ? theme.errorBg : theme.infoBg
    border.width: 1
    border.color: kind === "error" ? theme.errorFg : theme.infoFg

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 6
        anchors.topMargin: 6
        anchors.bottomMargin: 6
        spacing: 8

        Label {
            objectName: "toastText"
            Layout.fillWidth: true
            text: (toast.kind === "error" ? "⚠ " : "") + toast.message
            wrapMode: Text.Wrap
            font.pixelSize: theme.body
            color: toast.kind === "error" ? theme.errorFg : theme.infoFg
        }
        HaiButton {
            objectName: "toastAction"
            visible: toast.actionLabel !== ""
            text: toast.actionLabel
            kind: "secondary"
            textSize: theme.small
            onClicked: toast.action()
        }
        HaiButton {
            objectName: "toastClose"
            text: "✕"
            kind: "ghost"
            Accessible.name: "Fechar aviso"
            onClicked: toast.dismissed()
        }
    }
}
