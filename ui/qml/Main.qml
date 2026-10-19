// Janela principal: pilha de telas (menu → módulo) e o teclado da tela.
// A navegação é decidida em Python (core/app.py, AppController); aqui só se
// empilha e desempilha o que ele pede.
import QtQuick
import QtQuick.Controls
import Hai

ApplicationWindow {
    id: window

    title: "HAI - IA na Educação"
    width: app.windowWidth
    height: app.windowHeight
    minimumWidth: 640
    minimumHeight: 400
    visible: true
    visibility: app.fullscreen ? Window.FullScreen : Window.Windowed
    color: theme.bg
    font.pixelSize: theme.body

    // Fechar a janela passa pelo encerramento ordenado (core/app.py).
    onClosing: (close) => {
        close.accepted = false
        app.quit()
    }

    // F11 alterna a tela cheia (manutenção com teclado físico). Esc fica livre
    // para os módulos cancelarem a operação em andamento.
    Shortcut {
        sequence: "F11"
        context: Qt.ApplicationShortcut
        onActivated: app.fullscreen = !app.fullscreen
    }

    Item {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        // O teclado não cobre a tela: ela encolhe para o espaço de cima.
        height: parent.height - (keyboard.item && keyboard.item.shown ? keyboard.item.height : 0)

        StackView {
            id: stack
            objectName: "stack"
            anchors.fill: parent
            initialItem: MenuPage {}

            pushEnter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150 }
                NumberAnimation { property: "x"; from: 24; to: 0; duration: 150; easing.type: Easing.OutCubic }
            }
            pushExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 150 } }
            popEnter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150 } }
            popExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }
        }
    }

    // Só carregado com [display] on_screen_keyboard: sem ele o QML nem importa
    // o QtQuick.VirtualKeyboard (o método de entrada é o do sistema).
    Loader {
        id: keyboard
        objectName: "keyboardLoader"
        active: app.onScreenKeyboard
        source: "Keyboard.qml"
        width: parent.width
        y: parent.height - (item && item.shown ? item.height : 0)
        z: 100
    }

    Connections {
        target: app
        function onPagePushed(url, controller) {
            stack.push(url, { "controller": controller })
        }
        function onPagePopped() {
            Qt.inputMethod.hide()
            stack.pop(null)
        }
    }
}
