// Botão da plataforma: alvo de toque ≥ 48 px, cores do tema por `kind`
// (primary, success, danger, secondary, ghost) e anel de foco no teclado físico.
// Tocar não tira o foco do campo de texto (focusPolicy: Qt.TabFocus), então o
// teclado da tela não fecha ao tocar em Enviar, Falar ou Foto.
import QtQuick
import QtQuick.Controls

Button {
    id: control

    property string kind: "primary"
    property int textSize: theme.button

    readonly property var colors: ({
        "primary": [theme.blue, theme.blueDark, "#ffffff"],
        "success": [theme.green, theme.greenDark, "#ffffff"],
        "danger": [theme.red, theme.redDark, "#ffffff"],
        "secondary": [theme.card, theme.pressed, theme.text],
        "ghost": ["transparent", theme.pressed, theme.text]
    })[kind] || [theme.blue, theme.blueDark, "#ffffff"]

    focusPolicy: Qt.TabFocus
    font.pixelSize: textSize
    font.bold: true
    leftPadding: 18
    rightPadding: 18
    topPadding: 10
    bottomPadding: 10
    implicitWidth: Math.max(theme.touchMin, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(theme.touchMin, implicitContentHeight + topPadding + bottomPadding)
    Accessible.name: text

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? control.colors[2] : theme.hint
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 10
        color: !control.enabled ? (control.kind === "ghost" ? "transparent" : theme.disabledBg)
             : control.down ? control.colors[1] : control.colors[0]
        border.width: control.visualFocus ? 3 : (control.kind === "secondary" ? 1 : 0)
        border.color: control.visualFocus ? theme.focusRing : theme.border
        Behavior on color { ColorAnimation { duration: 80 } }
    }
}
