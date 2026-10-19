// Tela "Conversar com a IA":
//
//   [← Menu]  Conversar com a IA                                    [ ⋯ ]
//   ┌ histórico (balões: aluno à direita, IA à esquerda) ────────────────┐
//   │                                               [ ↓ Nova resposta ]  │
//   └────────────────────────────────────────────────────────────────────┘
//   ⚠ aviso ou erro, com ação (só quando há algo a dizer)
//   ┌ editor: texto com fotos embutidas, na ordem de envio ──────────────┐
//   │ [● Falar] [Foto]          2 fotos · 18 palavras         [Enviar ➤]  │
//   └────────────────────────────────────────────────────────────────────┘
//
// O editor é a área principal: sempre visível e tocável. Enviar só fica ativo
// com conteúdo e vira Parar, no mesmo lugar, enquanto algo está em andamento.
// Com o teclado da tela aberto, o histórico vira a barra "Ver conversa" e o
// editor fica com todo o espaço. Ctrl+Enter envia, Enter quebra a linha, Esc
// cancela o que estiver em andamento.
//
// Tudo que aparece vem do controller (modules/chat/controller.py); os botões
// só chamam os slots dele.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai

Item {
    id: page
    objectName: "chatPage"

    property var controller
    readonly property bool keyboardOpen: Qt.inputMethod.visible && app.keyboardEnabled
    // Com o teclado aberto, o histórico vira uma prévia do fim da conversa.
    readonly property int previewHeight: 132

    function showKeyboard() {
        editor.forceActiveFocus()
        Qt.inputMethod.show()
    }
    property double now: Date.now()
    readonly property int minHistory: 160

    function clock(ms) {
        var s = Math.max(0, Math.floor(ms / 1000))
        var r = s % 60
        return Math.floor(s / 60) + ":" + (r < 10 ? "0" : "") + r
    }

    // Foto embutida no ponto tocado do editor (-1 se o toque não foi numa foto).
    function photoAtPoint(x, y) {
        var p = editor.positionAt(x, y)
        for (var c = p - 1; c <= p; c++) {
            if (c < 0)
                continue
            var id = page.controller.photoAt(c)
            if (id < 0)
                continue
            var a = editor.positionToRectangle(c)
            var b = editor.positionToRectangle(c + 1)
            var right = b.y === a.y ? b.x : a.x + 160
            if (x >= a.x && x <= right && y >= a.y && y <= a.y + a.height)
                return id
        }
        return -1
    }

    Timer {
        // Relógio de "Pensando… 0:12" e da gravação; só o que depende dele redesenha.
        interval: 400
        repeat: true
        running: page.visible
        onTriggered: page.now = Date.now()
    }

    Shortcut {
        sequence: "Escape"
        enabled: !moreMenu.visible && !preview.visible && !backDialog.visible && !newDialog.visible
        onActivated: page.controller.cancel()
    }

    // Altura que o cartão do editor precisa com o teclado aberto: o conteúdo
    // (até 120 px, uma linha de miniaturas) mais a barra de ações.
    readonly property real composerNeed: Math.max(theme.touchMin, Math.min(editorFlick.contentHeight, 120))
                                         + actions.implicitHeight + 18

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 4
        anchors.bottomMargin: 12
        spacing: 8

        PageHeader {
            id: header
            Layout.fillWidth: true
            title: "Conversar com a IA"
            onBack: page.controller.requestBack()

            HaiButton {
                id: moreButton
                objectName: "moreButton"
                text: "⋯"
                kind: "ghost"
                textSize: theme.title
                Accessible.name: "Mais opções"
                onClicked: moreMenu.visible ? moreMenu.close() : moreMenu.open()
            }
        }

        Rectangle {
            id: historyCard
            Layout.fillWidth: true
            // Teclado aberto: prévia com o que sobra depois do editor (até
            // previewHeight); some se não couber nem uma linha.
            readonly property real previewRoom: Math.min(page.previewHeight,
                column.height - header.height - page.composerNeed - 2 * column.spacing)
            visible: !page.keyboardOpen || previewRoom >= 48
            Layout.fillHeight: !page.keyboardOpen
            Layout.preferredHeight: page.keyboardOpen ? previewRoom : -1
            Layout.maximumHeight: page.keyboardOpen ? previewRoom : Number.POSITIVE_INFINITY
            Layout.minimumHeight: page.keyboardOpen ? previewRoom : page.minHistory
            color: theme.card
            radius: 12

            ListView {
                id: history
                objectName: "history"

                // Segue o fim enquanto o aluno não rolar para cima; se rolou e
                // chegou texto novo, aparece "↓ Nova resposta".
                property bool follow: true
                property bool unseen: false

                anchors.fill: parent
                anchors.margins: 12
                // Na prévia, os balões não passam por baixo do "▴ Ver tudo".
                anchors.rightMargin: page.keyboardOpen ? historyBar.width + 18 : 12
                clip: true
                spacing: 10
                boundsBehavior: Flickable.StopAtBounds
                model: page.controller.messageModel
                ScrollIndicator.vertical: ScrollIndicator {}

                onMovementEnded: {
                    follow = atYEnd
                    if (follow)
                        unseen = false
                }
                onContentHeightChanged: if (follow) Qt.callLater(history.positionViewAtEnd)
                // Abrir o teclado encolhe o histórico para a prévia: o fim
                // (a resposta mais recente) continua à vista.
                onHeightChanged: if (follow) Qt.callLater(history.positionViewAtEnd)

                delegate: Item {
                    id: row

                    required property int msgId
                    required property string role
                    required property string text
                    required property string status
                    required property string error
                    required property var parts
                    required property double startedAt
                    required property bool retry

                    readonly property bool mine: role === "user"
                    readonly property real maxText: history.width - 110 - 28

                    width: history.width
                    height: bubble.height

                    Rectangle {
                        id: bubble
                        objectName: "bubble_" + row.msgId
                        x: row.mine ? row.width - width : 0
                        width: row.mine ? content.implicitWidth + 28 : row.width - 110
                        height: content.implicitHeight + 20
                        radius: 14
                        color: row.mine ? theme.userBubble : theme.aiBubble

                        Column {
                            id: content
                            x: 14
                            y: 10
                            spacing: 6

                            Repeater {
                                model: row.mine ? row.parts : []
                                delegate: Item {
                                    required property var modelData
                                    width: modelData.kind === "photo" ? photo.width : partText.width
                                    height: modelData.kind === "photo" ? photo.height : partText.height
                                    Image {
                                        id: photo
                                        visible: modelData.kind === "photo"
                                        source: visible ? modelData.url : ""
                                        sourceSize.height: 120
                                        height: visible ? 120 : 0
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                    }
                                    Text {
                                        id: partText
                                        visible: modelData.kind === "text"
                                        text: visible ? modelData.text : ""
                                        textFormat: Text.PlainText
                                        width: Math.min(implicitWidth, row.maxText)
                                        wrapMode: Text.Wrap
                                        font.pixelSize: theme.body
                                        color: theme.text
                                    }
                                }
                            }

                            Text {
                                objectName: "replyText"
                                visible: !row.mine && row.text !== ""
                                width: row.maxText
                                text: row.text
                                textFormat: Text.MarkdownText
                                wrapMode: Text.Wrap
                                font.pixelSize: theme.body
                                color: theme.text
                            }

                            Text {
                                objectName: "replyStatus"
                                visible: text !== ""
                                width: row.maxText
                                wrapMode: Text.Wrap
                                font.pixelSize: row.status === "error" ? theme.body : theme.small
                                color: row.status === "error" ? theme.errorFg : theme.muted
                                text: row.status === "thinking"
                                      ? ["●○○", "○●○", "○○●"][Math.floor(page.now / 400) % 3]
                                        + "  Pensando… " + page.clock(page.now - row.startedAt)
                                      : row.status === "cancelled" ? "Resposta interrompida."
                                      : row.status === "error" ? "⚠ " + row.error : ""
                            }

                            HaiButton {
                                objectName: "retryButton"
                                visible: row.retry
                                text: "↻ Tentar de novo"
                                kind: "secondary"
                                textSize: theme.small
                                onClicked: page.controller.send()
                            }
                        }
                    }
                }
            }

            HaiButton {
                id: historyBar
                objectName: "historyBar"
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 6
                visible: page.keyboardOpen
                kind: "secondary"
                textSize: theme.small
                text: "▴ Ver tudo"
                Accessible.name: page.controller.historyLabel
                onClicked: Qt.inputMethod.hide()
            }

            HaiButton {
                objectName: "jumpButton"
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 12
                visible: history.unseen && !history.follow && !page.keyboardOpen
                text: "↓ Nova resposta"
                textSize: theme.small
                onClicked: {
                    history.follow = true
                    history.unseen = false
                    history.positionViewAtEnd()
                }
            }
        }

        Toast {
            objectName: "toast"
            Layout.fillWidth: true
            kind: page.controller.toastKind
            message: page.controller.toastText
            actionLabel: page.controller.toastAction
            onAction: page.controller.noticeAction(editor.cursorPosition)
            onDismissed: page.controller.dismissNotice()
        }

        Rectangle {
            id: composer
            objectName: "composer"
            Layout.fillWidth: true
            Layout.fillHeight: page.keyboardOpen
            Layout.preferredHeight: editorFlick.contentHeight + actions.implicitHeight + 18
            // Com o teclado aberto o espaço é curto (≈ 330 px em 1024 × 600): o
            // editor fica com o que o conteúdo pede (composerNeed) e a prévia
            // do histórico é que encolhe.
            Layout.minimumHeight: page.keyboardOpen ? page.composerNeed
                                                    : theme.touchMin + actions.implicitHeight + 18
            color: theme.card
            radius: 12
            border.width: editor.activeFocus ? 2 : 1
            border.color: editor.activeFocus ? theme.blue : theme.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 2
                spacing: 0

                Flickable {
                    id: editorFlick
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    contentWidth: width
                    ScrollIndicator.vertical: ScrollIndicator {}

                    TextArea.flickable: TextArea {
                        id: editor
                        objectName: "editor"
                        textFormat: TextEdit.RichText
                        wrapMode: TextEdit.Wrap
                        placeholderText: "Escreva sua pergunta…"
                        placeholderTextColor: theme.hint
                        font.pixelSize: theme.body
                        color: theme.text
                        selectByMouse: true
                        inputMethodHints: Qt.ImhNoPredictiveText
                        padding: 12
                        background: null

                        onTextChanged: page.controller.editorChanged()
                        // Toque numa miniatura abre a foto. A área só fica com o toque
                        // quando ele cai numa foto; qualquer outro vai para o editor
                        // (cursor, seleção, teclado da tela).
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.IBeamCursor
                            onPressed: (mouse) => {
                                var photo = page.photoAtPoint(mouse.x, mouse.y)
                                mouse.accepted = photo >= 0
                                if (photo >= 0)
                                    page.controller.openPhoto(photo)
                            }
                        }
                        Keys.onPressed: (event) => {
                            var enter = event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                            if (enter && (event.modifiers & Qt.ControlModifier)) {
                                page.controller.send()
                                event.accepted = true
                            } else if (event.matches(StandardKey.Paste)) {
                                var at = editor.selectionStart
                                if (editor.selectedText !== "")
                                    editor.remove(editor.selectionStart, editor.selectionEnd)
                                editor.cursorPosition = page.controller.pastePlain(at)
                                event.accepted = true
                            } else if (event.nativeScanCode !== 0) {
                                // O teclado da tela também gera eventos de tecla, mas só
                                // as teclas de hardware têm código de varredura: isto é um
                                // teclado físico, e o resumo passa a mostrar os atalhos.
                                page.controller.physicalKey()
                            }
                        }
                    }
                }

                RowLayout {
                    id: actions
                    Layout.fillWidth: true
                    Layout.margins: 8
                    spacing: 10

                    HaiButton {
                        objectName: "micButton"
                        kind: page.controller.micKind
                        enabled: page.controller.micEnabled
                        text: page.controller.recording
                              ? page.controller.micLabel + " " + page.clock(page.now - page.controller.recordingStartedAt)
                              : page.controller.micLabel
                        // Toque alterna; segurar e soltar também funciona (controller).
                        onPressed: page.controller.micPressed(editor.cursorPosition)
                        onReleased: page.controller.micReleased()
                        onCanceled: page.controller.micReleased()
                    }
                    HaiButton {
                        objectName: "photoButton"
                        visible: page.controller.photoVisible
                        kind: "secondary"
                        enabled: page.controller.photoEnabled
                        text: page.controller.photoLabel
                        onClicked: page.controller.takePhoto(editor.cursorPosition)
                    }
                    Label {
                        objectName: "summary"
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideLeft
                        text: page.controller.summary
                        font.pixelSize: theme.small
                        color: theme.muted
                    }
                    HaiButton {
                        objectName: "sendButton"
                        kind: page.controller.sendKind
                        enabled: page.controller.sendEnabled
                        text: page.controller.sendLabel
                        onClicked: page.controller.sendOrStop()
                    }
                }
            }
        }
    }

    Menu {
        id: moreMenu
        objectName: "moreMenu"

        property bool showKeyboardOnClose: false
        onClosed: {
            if (showKeyboardOnClose) {
                showKeyboardOnClose = false
                Qt.callLater(page.showKeyboard)
            }
        }
        x: page.width - width - 16
        y: 56
        width: 360
        topPadding: 8
        bottomPadding: 8

        MenuItem {
            objectName: "voiceItem"
            text: (page.controller.voiceOutput ? "✓  " : "     ") + "Ler respostas em voz alta"
            visible: page.controller.voiceOutputAvailable
            height: visible ? 56 : 0
            font.pixelSize: theme.body
            onTriggered: page.controller.setVoiceOutput(!page.controller.voiceOutput)
        }
        MenuItem {
            objectName: "keyboardItem"
            // Preferência: com ela desligada, o teclado da tela não aparece
            // (quem usa teclado físico ganha a tela inteira). Ligar abre o
            // teclado depois que o menu fecha (o menu devolve o foco ao fechar).
            text: (app.keyboardEnabled ? "✓  " : "     ") + "Teclado na tela"
            visible: app.onScreenKeyboard
            height: visible ? 56 : 0
            font.pixelSize: theme.body
            onTriggered: {
                app.keyboardEnabled = !app.keyboardEnabled
                if (app.keyboardEnabled)
                    moreMenu.showKeyboardOnClose = true
                else
                    Qt.inputMethod.hide()
            }
        }
        MenuItem {
            objectName: "newItem"
            height: 56
            font.pixelSize: theme.body
            contentItem: Text {
                leftPadding: 12
                text: "Nova conversa…"
                font.pixelSize: theme.body
                color: theme.errorFg
                verticalAlignment: Text.AlignVCenter
            }
            onTriggered: newDialog.open()
        }
    }

    Popup {
        id: preview
        objectName: "photoPreview"

        property int blockId: -1
        property bool isNew: false
        property string source: ""
        property string label: ""

        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        dim: true
        padding: 20
        closePolicy: Popup.CloseOnEscape
        Overlay.modal: Rectangle { color: theme.shade }
        background: Rectangle { color: theme.card; radius: 14 }
        onClosed: editor.forceActiveFocus()

        contentItem: ColumnLayout {
            spacing: 10
            Image {
                Layout.alignment: Qt.AlignHCenter
                source: preview.source
                sourceSize.width: 340
                sourceSize.height: 340
                fillMode: Image.PreserveAspectFit
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: preview.label
                font.pixelSize: theme.small
                color: theme.muted
            }
            RowLayout {
                spacing: 10
                Item { Layout.fillWidth: true }
                HaiButton {
                    objectName: preview.isNew ? "previewCancel" : "previewRemove"
                    text: preview.isNew ? "Cancelar" : "Remover foto"
                    kind: preview.isNew ? "secondary" : "danger"
                    onClicked: {
                        preview.close()
                        page.controller.removePhoto(preview.blockId)
                    }
                }
                HaiButton {
                    objectName: "previewRetake"
                    visible: preview.isNew
                    text: "Tirar outra"
                    kind: "secondary"
                    onClicked: {
                        preview.close()
                        page.controller.retakePhoto(preview.blockId)
                    }
                }
                HaiButton {
                    objectName: preview.isNew ? "previewUse" : "previewClose"
                    text: preview.isNew ? "Usar foto" : "Fechar"
                    onClicked: preview.close()
                }
            }
        }
    }

    ConfirmDialog {
        id: backDialog
        objectName: "backDialog"
        title: "Sair da conversa?"
        message: "Sua pergunta e a conversa serão apagadas. Nada fica salvo."
        confirmLabel: "Sair"
        cancelLabel: "Continuar aqui"
        onConfirmed: page.controller.back()
    }

    ConfirmDialog {
        id: newDialog
        objectName: "newDialog"
        title: "Apagar esta conversa?"
        message: "As mensagens e a pergunta em edição somem. Nada fica salvo."
        confirmLabel: "Apagar"
        onConfirmed: page.controller.newConversation()
    }

    // Texto novo com o histórico rolado para cima: avisa pelo modelo, não pela
    // altura do conteúdo (o ListView nem cria o balão do fim fora da tela).
    Connections {
        target: page.controller.messageModel
        function onDataChanged() {
            if (!history.follow)
                history.unseen = true
        }
        function onRowsInserted() {
            if (!history.follow)
                history.unseen = true
        }
    }

    Connections {
        target: page.controller
        function onFocusEditor(position) {
            editor.cursorPosition = Math.min(position, editor.length)
            editor.forceActiveFocus()
        }
        function onSent() {
            history.follow = true
            history.unseen = false
            Qt.inputMethod.hide()
            editor.focus = false
        }
        function onPhotoPreview(blockId, isNew, source, label) {
            preview.blockId = blockId
            preview.isNew = isNew
            preview.source = source
            preview.label = label
            preview.open()
        }
        function onConfirmRequested(kind) {
            if (kind === "back")
                backDialog.open()
        }
    }

    Component.onCompleted: page.controller.attachEditor(editor.textDocument)
}
