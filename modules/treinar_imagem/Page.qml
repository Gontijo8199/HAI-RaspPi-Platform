// Tela "Treinar reconhecedor":
//
//   [← Menu]  Treinar reconhecedor
//   ┌ classes ─────────────┐ ┌ prévia ao vivo + previsões ────────────┐
//   │ [Classe 1 ] 3 fotos + │ │  Classe 1  ████████░░  67%             │
//   │ [Classe 2 ] 1 foto  + │ │  Classe 2  ███░░░░░░░  33%             │
//   │ [+ Nova classe]       │ │                                        │
//   │ [Treinar modelo]      │ │                [Testar]                │
//   │ status                │ └────────────────────────────────────────┘
//
// A prévia mostra a câmera ao vivo; "+" e "Testar" usam o quadro que está na
// tela. Se a prévia não abrir, cada toque tira uma foto (e ela aparece aqui).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai

Item {
    id: page
    objectName: "trainerPage"

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
                Layout.preferredWidth: 340
                Layout.fillWidth: false  // os filhos com fillWidth não esticam a coluna
                Layout.fillHeight: true
                spacing: 10

                ListView {
                    id: classList
                    objectName: "classList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8
                    boundsBehavior: Flickable.StopAtBounds
                    model: page.controller ? page.controller.classes : null

                    delegate: Rectangle {
                        required property int index
                        required property string name
                        required property int photos
                        width: ListView.view.width
                        height: 64
                        radius: 12
                        color: theme.card
                        border.width: 1
                        border.color: theme.divider

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 8
                            TextField {
                                objectName: "className" + index
                                Layout.fillWidth: true
                                text: name
                                font.pixelSize: theme.body
                                font.bold: true
                                color: theme.text
                                inputMethodHints: Qt.ImhNoPredictiveText
                                background: Rectangle {
                                    color: "transparent"
                                    radius: 8
                                    border.width: parent.activeFocus ? 2 : 0
                                    border.color: theme.blue
                                }
                                onEditingFinished: page.controller.rename(index, text)
                            }
                            Label {
                                text: photos === 1 ? "1 foto" : photos + " fotos"
                                font.pixelSize: theme.small
                                color: theme.muted
                            }
                            HaiButton {
                                objectName: "addPhoto" + index
                                text: "+"
                                textSize: theme.title
                                enabled: page.controller && !page.controller.busy
                                Accessible.name: "Tirar foto para " + name
                                onClicked: page.controller.addPhoto(index)
                            }
                        }
                    }
                }

                HaiButton {
                    objectName: "newClassButton"
                    Layout.fillWidth: true
                    text: "+ Nova classe"
                    kind: "secondary"
                    onClicked: {
                        page.controller.newClass()
                        classList.positionViewAtEnd()
                    }
                }
                HaiButton {
                    objectName: "trainButton"
                    Layout.fillWidth: true
                    text: "Treinar modelo"
                    kind: "success"
                    enabled: page.controller && !page.controller.busy
                    onClicked: page.controller.train()
                }
                Label {
                    objectName: "status"
                    Layout.fillWidth: true
                    Layout.minimumHeight: 44
                    text: page.controller ? page.controller.status : ""
                    wrapMode: Text.Wrap
                    font.pixelSize: theme.small
                    color: page.controller && page.controller.error ? theme.errorFg : theme.muted
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 12
                color: theme.card
                clip: true

                Label {
                    anchors.centerIn: parent
                    visible: !photo.visible
                    width: parent.width - 40
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: "Ligando a câmera…"
                    font.pixelSize: theme.body
                    color: theme.hint
                }

                Image {
                    id: photo
                    objectName: "photo"
                    anchors.fill: parent
                    anchors.margins: 8
                    visible: source != ""
                    source: page.controller ? page.controller.photo : ""
                    fillMode: Image.PreserveAspectFit
                    sourceSize.width: 640
                    // Síncrona e sem cache: cada quadro da prévia troca o endereço;
                    // assíncrona piscaria entre um quadro e outro.
                    cache: false
                }

                // Previsões do último teste, por cima da foto.
                Rectangle {
                    objectName: "predictions"
                    visible: page.controller && page.controller.trained
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.margins: 12
                    width: 300
                    height: bars.implicitHeight + 20
                    radius: 12
                    color: "#f0ffffff"
                    border.width: 1
                    border.color: theme.border

                    Column {
                        id: bars
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 6
                        Repeater {
                            model: page.controller ? page.controller.classes : null
                            delegate: RowLayout {
                                required property string name
                                required property real confidence
                                required property var winner
                                width: bars.width
                                spacing: 8
                                Label {
                                    Layout.preferredWidth: 100
                                    text: name
                                    elide: Text.ElideRight
                                    font.pixelSize: theme.small
                                    color: theme.text
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 12
                                    radius: 6
                                    color: theme.disabledBg
                                    Rectangle {
                                        width: parent.width * confidence
                                        height: parent.height
                                        radius: 6
                                        color: winner === true ? theme.green : theme.blue
                                    }
                                }
                                Label {
                                    Layout.preferredWidth: 44
                                    horizontalAlignment: Text.AlignRight
                                    text: Math.round(confidence * 100) + "%"
                                    font.pixelSize: theme.small
                                    font.bold: true
                                    color: theme.text
                                }
                            }
                        }
                    }
                }

                HaiButton {
                    objectName: "testButton"
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 12
                    text: "Testar"
                    enabled: page.controller && !page.controller.busy
                    onClicked: page.controller.test()
                }
            }
        }
    }
}
