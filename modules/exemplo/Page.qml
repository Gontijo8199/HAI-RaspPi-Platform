// Tela do módulo de exemplo:
//
//   [← Menu]  Módulo de exemplo
//   Digite um número inteiro e toque em Verificar.
//   [ campo ]  [Verificar]  [Limpar]
//   ┌ resultado (ou aviso de entrada inválida) ─────────────────────────┐
//   └───────────────────────────────────────────────────────────────────┘
//
// O campo pede só algarismos (Qt.ImhDigitsOnly): o teclado da tela já abre
// no layout numérico. A tela não calcula nada: chama controller.check().
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai

Item {
    id: page
    objectName: "examplePage"

    property var controller

    function check() {
        if (!page.controller.check(field.text))
            field.selectAll()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        anchors.topMargin: 12
        anchors.bottomMargin: 12
        spacing: 10

        PageHeader {
            Layout.fillWidth: true
            title: page.controller ? page.controller.title : ""
            onBack: page.controller.back()
        }

        Label {
            Layout.fillWidth: true
            text: "Digite um número inteiro (de 1 a 1.000.000) e toque em Verificar para ver seus divisores e se ele é primo."
            wrapMode: Text.Wrap
            font.pixelSize: theme.small
            color: theme.muted
        }

        RowLayout {
            spacing: 12
            TextField {
                id: field
                objectName: "numberField"
                Layout.preferredWidth: 240
                font.pixelSize: theme.title
                inputMethodHints: Qt.ImhDigitsOnly | Qt.ImhNoPredictiveText
                placeholderText: "Ex.: 28"
                placeholderTextColor: theme.hint
                color: theme.text
                topPadding: 10
                bottomPadding: 10
                background: Rectangle {
                    color: theme.card
                    radius: 10
                    border.width: field.activeFocus ? 2 : 1
                    border.color: field.activeFocus ? theme.blue : theme.border
                }
                onAccepted: page.check()
            }
            HaiButton {
                objectName: "checkButton"
                text: "Verificar"
                onClicked: page.check()
            }
            HaiButton {
                objectName: "clearButton"
                text: "Limpar"
                kind: "secondary"
                onClicked: {
                    field.clear()
                    page.controller.clear()
                    field.forceActiveFocus()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: theme.card
            radius: 12

            Flickable {
                anchors.fill: parent
                anchors.margins: 18
                clip: true
                contentHeight: result.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: result
                    width: parent.width
                    spacing: 8
                    Label {
                        objectName: "verdict"
                        Layout.fillWidth: true
                        text: page.controller ? page.controller.verdict : ""
                        font.pixelSize: theme.title
                        font.bold: true
                        color: page.controller && page.controller.error ? theme.errorFg : theme.text
                        wrapMode: Text.Wrap
                    }
                    Label {
                        objectName: "details"
                        Layout.fillWidth: true
                        text: page.controller ? page.controller.details : ""
                        font.pixelSize: theme.body
                        color: theme.text
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }

    // No fim da animação de entrada (o StackView mexe no foco durante ela).
    StackView.onActivated: field.forceActiveFocus()
}
