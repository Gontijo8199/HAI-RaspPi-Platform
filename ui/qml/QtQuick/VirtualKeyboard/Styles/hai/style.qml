// Estilo claro do teclado da tela, nas cores da plataforma (ui/theme.py:
// CARD, BG, DIVIDER, PRESSED, TEXT, BLUE). O estilo padrão do Qt Virtual
// Keyboard é escuro e destoava da interface.
//
// O Qt procura estilos em <caminho de import>/QtQuick/VirtualKeyboard/Styles/<nome>;
// ui/qml é um caminho de import da aplicação, e Keyboard.qml escolhe "hai".
// Símbolos de texto no lugar de ícones: sem imagens para manter.
import QtQuick
import QtQuick.VirtualKeyboard
import QtQuick.VirtualKeyboard.Styles
import "Palette.js" as Palette

KeyboardStyle {
    id: haiStyle

    readonly property real margin: Math.round(4 * scaleHint)
    readonly property real radius: Math.round(8 * scaleHint)
    readonly property int letterSize: Math.round(30 * scaleHint)
    readonly property int labelSize: Math.round(20 * scaleHint)

    // Proporção do teclado: 1024 × 270 numa tela de 1024 × 600 deixa espaço
    // para o editor e a barra de ações acima dele.
    keyboardDesignWidth: 1024
    keyboardDesignHeight: 270
    keyboardRelativeLeftMargin: 6 / 1024
    keyboardRelativeRightMargin: 6 / 1024
    keyboardRelativeTopMargin: 6 / 270
    keyboardRelativeBottomMargin: 6 / 270

    keyboardBackground: Rectangle { color: Palette.background }

    keyPanel: KeyPanel {
        KeyBox {
            down: control.pressed
            scaleHint: haiStyle.scaleHint
            Text {
                // acento disponível ao segurar a tecla
                visible: control.smallTextVisible
                text: control.smallText
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: haiStyle.margin * 1.5
                color: Palette.muted
                font.pixelSize: Math.round(haiStyle.labelSize * 0.7)
            }
            Text {
                anchors.centerIn: parent
                text: control.displayText
                color: Palette.text
                font.pixelSize: haiStyle.letterSize
                font.capitalization: control.uppercased ? Font.AllUppercase : Font.MixedCase
            }
        }
    }

    backspaceKeyPanel: KeyPanel {
        KeyBox { special: true; down: control.pressed; scaleHint: haiStyle.scaleHint; label: "⌫"; labelSize: haiStyle.letterSize }
    }

    enterKeyPanel: KeyPanel {
        KeyBox {
            accent: true
            down: control.pressed
            scaleHint: haiStyle.scaleHint
            label: control.displayText !== "" ? control.displayText : "⏎"
            labelSize: haiStyle.letterSize
        }
    }

    shiftKeyPanel: KeyPanel {
        KeyBox {
            special: true
            accent: InputContext.capsLockActive || InputContext.shiftActive
            down: control.pressed
            scaleHint: haiStyle.scaleHint
            label: InputContext.capsLockActive ? "⇪" : "⇧"
            labelSize: haiStyle.letterSize
        }
    }

    spaceKeyPanel: KeyPanel {
        KeyBox { down: control.pressed; scaleHint: haiStyle.scaleHint; label: "espaço"; labelColor: Palette.muted }
    }

    symbolKeyPanel: KeyPanel {
        KeyBox { special: true; down: control.pressed; scaleHint: haiStyle.scaleHint; label: control.displayText }
    }

    modeKeyPanel: KeyPanel {
        KeyBox { special: true; down: control.pressed; scaleHint: haiStyle.scaleHint; label: control.displayText }
    }

    hideKeyPanel: KeyPanel {
        KeyBox { special: true; down: control.pressed; scaleHint: haiStyle.scaleHint; label: "⌄"; labelSize: haiStyle.letterSize }
    }

    languageKeyPanel: KeyPanel {
        KeyBox { special: true; down: control.pressed; scaleHint: haiStyle.scaleHint; label: "🌐" }
    }

    characterPreviewMargin: 0
    characterPreviewDelegate: Item {
        property string text
        Rectangle {
            anchors.fill: parent
            radius: haiStyle.radius
            color: Palette.key
            border.width: 1
            border.color: Palette.border
            Text {
                anchors.centerIn: parent
                text: parent.parent.text
                color: Palette.text
                font.pixelSize: Math.round(haiStyle.letterSize * 1.3)
            }
        }
    }

    // Acentos ao segurar a tecla.
    alternateKeysListItemWidth: Math.round(64 * scaleHint)
    alternateKeysListItemHeight: Math.round(72 * scaleHint)
    alternateKeysListDelegate: Item {
        id: alternate
        width: haiStyle.alternateKeysListItemWidth
        height: haiStyle.alternateKeysListItemHeight
        Text {
            anchors.centerIn: parent
            text: model.text
            color: alternate.ListView.isCurrentItem ? "#ffffff" : Palette.text
            font.pixelSize: haiStyle.letterSize
        }
    }
    alternateKeysListHighlight: Rectangle { color: Palette.accent; radius: haiStyle.radius }
    alternateKeysListBackground: Rectangle {
        color: Palette.key
        radius: haiStyle.radius
        border.width: 1
        border.color: Palette.border
    }

    // Lista de sugestões (fica vazia: a predição está desligada nos campos).
    selectionListHeight: Math.round(56 * scaleHint)
    selectionListDelegate: SelectionListItem {
        id: candidate
        width: Math.max(80, word.implicitWidth + 24)
        Text {
            id: word
            anchors.centerIn: parent
            text: decorateText(display, wordCompletionLength)
            color: Palette.text
            font.pixelSize: haiStyle.labelSize
            function decorateText(text, wordCompletionLength) {
                return text
            }
        }
    }
    selectionListHighlight: Rectangle { color: Palette.specialKey; radius: haiStyle.radius }
    selectionListBackground: Rectangle { color: Palette.background }

    navigationHighlight: Rectangle {
        color: "transparent"
        border.color: Palette.accent
        border.width: 3
        radius: haiStyle.radius
    }

    popupListDelegate: SelectionListItem {
        width: haiStyle.alternateKeysListItemWidth * 3
        height: haiStyle.alternateKeysListItemHeight
        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 12
            text: languageNameFormatter.elidedText
            color: Palette.text
            font.pixelSize: haiStyle.labelSize
            TextMetrics { id: languageNameFormatter; text: displayName }
        }
    }
    popupListHighlight: Rectangle { color: Palette.specialKey; radius: haiStyle.radius }
    popupListBackground: Rectangle {
        color: Palette.key
        radius: haiStyle.radius
        border.width: 1
        border.color: Palette.border
    }
}
