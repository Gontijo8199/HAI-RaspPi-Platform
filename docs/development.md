# Desenvolvimento

## Ambiente

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt     # inclui requirements.txt
python core/main.py --windowed --no-tts # janela 1024 × 600, sem áudio
```

Sem `config/secrets.toml`, o chat fica indisponível no menu, e o resto da
interface e o módulo de exemplo funcionam normalmente.

## Convenções

- Mensagens, comentários e documentação em português; nomes de código em
  inglês, exceto onde o código existente já usa português (`api/llm_client.py`).
- `ruff check .` e `ruff format --check .` passam no CI (`ruff.toml`: linha de
  100 colunas).
- Lógica de módulo sem interface: regra de negócio em um arquivo que não
  importa Qt, testável com pytest puro (`modules/exemplo/logic.py`,
  `modules/chat/session.py`).
- O controller (`QObject`) entrega à tela o estado pronto para desenhar
  (rótulos, `kind` dos botões, habilitado) e recebe as ações em slots. A
  `Page.qml` só lê e chama: sem regra, sem estado da atividade, sem decidir
  texto de botão.
- Serviços caros vêm de `self.services`; módulos não criam clientes de LLM,
  TTS, câmera ou Whisper próprios.
- Interface de toque: alvos de pelo menos 48 × 48 px (`HaiButton` garante),
  nada que dependa de hover.
- Cores só de `ui/theme.py` (na QML, `theme.<nome>`). Um par texto/fundo novo
  entra em `CONTRAST_PAIRS` (o teste exige WCAG AA). Estado nunca só por cor:
  acompanhe com texto ou símbolo (⚠, ✓, ■).
- Uma ação principal por área (botão preenchido); o resto, `secondary` ou
  `ghost`. Ações destrutivas passam por `ConfirmDialog`; erros, por `Toast`
  (persistentes, com ação de recuperação quando houver uma).
- Todo item que um teste precisa achar ganha `objectName`.
- Logs: sem prompts, transcrições, respostas completas, imagens ou chaves.
  Registre tipos de erro, tamanhos e estados.
- Comentários explicam decisões, restrições de hardware, concorrência e
  invariantes, não o que a linha seguinte faz.

## Criar um módulo

O módulo de exemplo (`modules/exemplo/`) é a referência mínima:

| Arquivo | Papel |
|---|---|
| `logic.py` | regra da atividade, sem Qt |
| `controller.py` | `QObject`: estado da tela (propriedades com `notify`) e ações (slots); chama a lógica |
| `Page.qml` | a tela: lê `controller`, chama os slots |
| `icon.svg` | ícone do cartão do menu |
| `module.py` | registro (`id`, `title`, `summary`) e ciclo de vida (`enter`/`exit`) |

Passos:

1. Crie `modules/<nome>/` com esses arquivos e um `__init__.py` que exporte
   a classe do módulo.
2. Na classe, herde de `modules.base.Module`, defina `id`, `title`,
   opcionalmente `summary` e, se o módulo depender de algum serviço,
   `unavailable_reason()`. `icon` e `page` já apontam para `icon.svg` e
   `Page.qml` da pasta.
3. Em `enter(go_back)`, adquira os recursos da atividade e devolva o
   controller. Ligue o "← Menu" da página a um slot que chama `go_back`.
4. Em `exit()`, cancele tarefas e timers e libere os recursos. Marque o
   controller como fechado: a página ainda o lê durante a animação de saída,
   e todo slot deve ignorar chamadas depois disso.
5. Registre o módulo em `REGISTRY`, em `modules/__init__.py`: uma fábrica que
   importa a classe e o estado padrão (ativo ou não). A ordem do dicionário é
   a ordem do menu. `core/main.py` e `core/app.py` não mudam.

   Desativar um módulo (no `REGISTRY` ou com `[modules] <id> = false` no
   `settings.toml`) só o tira do menu: os testes montam a interface com
   `build_modules(services, enabled=list(REGISTRY))` e continuam exercitando
   todos os módulos registrados. `tests/test_modules_registry.py` cobre a seleção.
6. Escreva os testes (veja abaixo) e um `README.md` do módulo.

Esqueleto da página:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Hai                      // HaiButton, PageHeader, Toast, ConfirmDialog

Item {
    id: page
    property var controller     // entregue pela App

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        PageHeader {
            Layout.fillWidth: true
            title: page.controller ? page.controller.title : ""
            onBack: page.controller.back()
        }
        TextField {             // tocar abre o teclado da tela
            inputMethodHints: Qt.ImhDigitsOnly   // já no layout numérico
        }
    }
}
```

O teclado da tela abre sozinho em qualquer campo de texto (`TextField`,
`TextArea`): não há nada a ligar. Use `inputMethodHints` para o layout
(`Qt.ImhDigitsOnly`, `Qt.ImhNoPredictiveText`...).

Para trabalho assíncrono (rede, arquivos, hardware), guarde as tarefas criadas
e cancele-as em `exit()`, como `ChatModule._spawn` faz. Um resultado que chegue
depois da saída não pode mudar o estado da tela.

## Testes

```bash
pytest                       # tudo, inclusive a interface (Qt offscreen, sem servidor gráfico)
pytest tests/test_exemplo_logic.py -v
```

O `tests/conftest.py` põe `QT_QPA_PLATFORM=offscreen` antes de criar a
`QGuiApplication`: a QML roda e desenha em memória, com o teclado da tela de
verdade. Não é preciso Xvfb.

| Arquivo | Cobre |
|---|---|
| `test_exemplo_logic.py` | validação e cálculo do módulo de exemplo |
| `test_chat_session.py` | lógica do chat: rascunho, envio, erros, cancelamento, nova conversa, resultados atrasados |
| `test_chat_controller.py` | estado e ações da tela do chat, sem QML: rótulos, Enviar/Parar, fotos, voz, avisos, streaming agrupado |
| `test_chat_editor.py` | editor com fotos embutidas (`QTextDocument`): ordem visual, ⌫, redesenho incremental |
| `test_chat_page.py` | a tela do chat em QML: toques, atalhos, prévia da foto, diálogos, "Nova resposta" |
| `test_keyboard.py` | teclado da tela integrado: abre, tem altura, escreve, estilo claro, layout numérico, ligar/desligar |
| `test_app.py` | menu (1, N, mais de 6 e 0 módulos; abrir direto), navegação e limpeza de recursos, módulo de exemplo |
| `test_main.py` | linha de comando, `main()` (sem tela → código 1), método de entrada |
| `test_llm_client.py` | montagem multimodal, streaming, cancelamento, erros legíveis (google-genai simulado) |
| `test_services.py` | configuração, Whisper compartilhado, preferências |
| `test_theme.py` | contraste WCAG de todos os pares de cor declarados |
| `test_recorder.py`, `test_chunker.py`, `test_camera.py`, `test_tts_speaker.py`, `test_whisper_engine.py` | integrações isoladas, com dublês de hardware |

Fixtures (`qapp`, `make_app`) ficam em `tests/conftest.py`; utilitários em
`tests/qthelpers.py`:
- `pump` e `until`: rodam o Qt e o asyncio juntos;
- `find`, `find_all` e `items`: acham itens pelo `objectName`;
- `click`, `key` e `type_text`: toque e teclado;
- `screen_items`: contagem sem o teclado.

Dublês ficam em `tests/fakes.py` (`FakeServices`, `FakeLLM`, `FakeRecorder`,
`FakeCamera`…). Eles substituem os serviços só nos testes; a aplicação usa os
reais.

Organização sugerida para um módulo novo:

- `tests/test_<nome>_logic.py` para a lógica, sem Qt;
- testes do controller sem QML, se ele tiver estado próprio;
- em `tests/test_app.py`, um teste que abre o módulo pelo `App`, toca na tela
  e volta ao menu; inclua também o módulo em
  `test_navegacao_repetida_nao_acumula_recursos`.

O que os testes automáticos não cobrem: microfone, alto-falante e webcam
reais, a API real do LLM, a tela de toque física e o desempenho no Raspberry Pi.
