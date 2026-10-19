// Teclado da tela: o Qt Virtual Keyboard em português do Brasil (acentos ao
// segurar a tecla; layout numérico nos campos com Qt.ImhDigitsOnly).
// Estilo claro próprio ("hai"), nas cores da plataforma. A altura do teclado
// segue a largura; numa tela mais quadrada ele ficaria alto demais, então a
// largura é limitada para a altura não passar de 46% da janela.
import QtQuick
import QtQuick.Window
import QtQuick.VirtualKeyboard
import QtQuick.VirtualKeyboard.Settings

Item {
    id: root

    readonly property alias active: panel.active
    // Desligado no menu ⋯ ("Teclado na tela"): o painel não aparece e o
    // campo continua recebendo o teclado físico.
    readonly property bool shown: panel.active && app.keyboardEnabled
    // Da janela, não do Loader: a altura do Loader é a do próprio teclado
    // (usá-la aqui fecha um laço que zera a altura e o teclado some).
    readonly property real maxHeight: Window.height * 0.46

    height: panel.height

    InputPanel {
        id: panel
        objectName: "inputPanel"
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(root.width, root.maxHeight * panel.ratio)
        visible: app.keyboardEnabled
        // largura / altura do estilo "hai" (keyboardDesignWidth / keyboardDesignHeight)
        readonly property real ratio: 1024 / 270
    }

    Component.onCompleted: {
        VirtualKeyboardSettings.styleName = "hai"  // ui/qml/QtQuick/VirtualKeyboard/Styles/hai
        VirtualKeyboardSettings.locale = "pt_BR"
        VirtualKeyboardSettings.activeLocales = ["pt_BR"]
    }
}
