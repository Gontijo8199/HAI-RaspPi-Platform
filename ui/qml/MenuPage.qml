// Menu principal: um cartão por módulo ativo (modules.REGISTRY).
//   1 módulo: cartão grande e centralizado;
//   2 a 6: grade centralizada de até 3 colunas;
//   mais: a mesma grade rola por arrasto, com o título fixo;
//   0: só o aviso de configuração.
// Um módulo indisponível (ex.: sem chave da API) continua visível, com o
// motivo curto no cartão; o toque mostra o motivo completo no rodapé.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai

Item {
    id: page
    objectName: "menuPage"

    readonly property int count: app.modules.length
    readonly property bool hero: count === 1
    readonly property int columns: Math.max(1, Math.min(3, count))

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 32
        anchors.rightMargin: 32
        anchors.topMargin: 24
        anchors.bottomMargin: 20
        spacing: 12

        Label {
            text: "Escolha uma atividade"
            font.pixelSize: theme.title
            font.bold: true
            color: theme.text
        }

        Flickable {
            id: scroller
            objectName: "menuScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: Math.max(height, grid.implicitHeight + 16)
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            ScrollIndicator.vertical: ScrollIndicator {}

            Grid {
                id: grid
                anchors.horizontalCenter: parent.horizontalCenter
                y: page.hero ? Math.max(0, (scroller.height - implicitHeight) / 2) : 8
                columns: page.columns
                spacing: 20

                Repeater {
                    model: app.modules
                    ModuleCard {
                        objectName: "card_" + modelData.id
                        module: modelData
                        hero: page.hero
                        onClicked: app.open(modelData.id)
                    }
                }
            }
        }

        Label {
            objectName: "menuMessage"
            Layout.fillWidth: true
            visible: app.menuMessage !== ""
            text: "⚠ " + app.menuMessage
            wrapMode: Text.Wrap
            font.pixelSize: theme.body
            color: theme.errorFg
            padding: 12
            leftPadding: 16
            background: Rectangle { color: theme.errorBg; radius: 10 }
        }
    }
}
