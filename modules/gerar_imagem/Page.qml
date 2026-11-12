// Tela "Gerar imagem":
//
//   [← Menu]  Gerar imagem
//   Descreva a imagem:          ┌ imagem gerada ─────────────────┐
//   [ área de texto        ]    │                                │
//   [Gerar imagem]              │                                │
//   status                      └────────────────────────────────┘
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai

Item {
    id: page
    objectName: "imageGenPage"

    property var controller

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

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            ColumnLayout {
                Layout.preferredWidth: 360
                Layout.fillWidth: false  // os filhos com fillWidth não esticam a coluna
                Layout.fillHeight: true
                spacing: 10

                Label {
                    text: "Descreva a imagem:"
                    font.pixelSize: theme.body
                    font.bold: true
                    color: theme.text
                }
                TextArea {
                    id: prompt
                    objectName: "promptField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 150
                    wrapMode: TextArea.Wrap
                    font.pixelSize: theme.body
                    color: theme.text
                    placeholderText: "Ex.: um gato astronauta andando de patinete na lua"
                    placeholderTextColor: theme.hint
                    background: Rectangle {
                        color: theme.card
                        radius: 10
                        border.width: prompt.activeFocus ? 2 : 1
                        border.color: prompt.activeFocus ? theme.blue : theme.border
                    }
                }
                HaiButton {
                    objectName: "generateButton"
                    Layout.fillWidth: true
                    text: page.controller && page.controller.busy ? "Gerando…" : "Gerar imagem"
                    enabled: page.controller && !page.controller.busy
                    onClicked: page.controller.generate(prompt.text)
                }
                Label {
                    objectName: "status"
                    Layout.fillWidth: true
                    text: page.controller ? page.controller.status : ""
                    wrapMode: Text.Wrap
                    font.pixelSize: theme.small
                    color: page.controller && page.controller.error ? theme.errorFg : theme.muted
                }
                Item { Layout.fillHeight: true }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 12
                color: theme.card
                clip: true

                Label {
                    anchors.centerIn: parent
                    visible: !result.visible
                    text: page.controller && page.controller.busy ? "Desenhando…" : "A imagem gerada aparece aqui"
                    font.pixelSize: theme.body
                    color: theme.hint
                }
                Image {
                    id: result
                    objectName: "result"
                    anchors.fill: parent
                    anchors.margins: 8
                    visible: source != ""
                    source: page.controller ? page.controller.image : ""
                    fillMode: Image.PreserveAspectFit
                    sourceSize.width: 640
                    asynchronous: true
                }
            }
        }
    }

    StackView.onActivated: prompt.forceActiveFocus()
}
