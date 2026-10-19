# Arquitetura

## Visão geral

```
core/main.py      linha de comando e log → core.app.main()
core/app.py       configuração do Qt, janela, menu, navegação, ciclo de vida, encerramento
core/services.py  configuração e serviços compartilhados (LLM, TTS, câmera, Whisper)
modules/          um pacote por atividade; base.py define o contrato
ui/               tema, modelos, imagens e a QML comum (janela, menu, componentes, teclado)
api/ stt/ tts/ vision/   integrações usadas pelos serviços e módulos
```

```
python core/main.py ─► main() ─► load_config ─► Services ─► QGuiApplication ─► App.run() (qasync)
                                                                                 │
                 menu (ui/qml/MenuPage.qml) ◄── voltar ── página do módulo ◄─────┘
                                                          (controller.py + Page.qml)
```

`core/main.py` não conhece nenhum módulo: só lê `--windowed`, `--no-tts` e
`--tts-backend`, configura o log e chama `main()`. A lista de módulos vem de
`modules.build_modules()`, que instancia os módulos ativos de `REGISTRY`
(padrão no código, sobrescrito por `[modules]` no `settings.toml`). Com
nenhum módulo ativo, o menu mostra um aviso.

## Interface: Qt Quick (QML)

A tela é Qt Quick, via PySide6: desenhada pela GPU, Wayland nativo e com o
que a plataforma precisava pronto, em vez de feito à mão como na versão em Tk:

| Necessidade | Biblioteca |
|---|---|
| teclado na tela pt-BR, acentos ao segurar a tecla, layout numérico | Qt Virtual Keyboard (`InputPanel`) |
| rolagem por toque com inércia | `Flickable` / `ListView` |
| Markdown nas respostas | `Text.MarkdownText` |
| editor com fotos no meio do texto | `TextArea` em rich text + `QTextDocument` |
| diálogos, menu ⋯, prévia da foto | `Popup`, `Menu` (Qt Quick Controls, estilo Basic) |
| imagens das fotos (JPEG em memória) | `QQuickImageProvider` (`ui/images.py`) |

Divisão de trabalho, em todo módulo:

- **controller (Python, `QObject`)**: estado já pronto para desenhar
  (rótulos, cores, habilitado), em propriedades com sinal de mudança, e as
  ações em slots. É testado sem QML.
- **Page.qml**: só lê o controller e chama os slots. Não decide nada.

A QML comum fica em `ui/qml/`:

| Arquivo | Papel |
|---|---|
| `Main.qml` | janela, pilha de telas (`StackView`, com o menu na base) e o teclado |
| `Keyboard.qml` | o `InputPanel` do Qt Virtual Keyboard, em pt-BR |
| `MenuPage.qml` | grade de cartões dos módulos |
| `Hai/` (`import Hai`) | `HaiButton`, `PageHeader`, `Toast`, `ConfirmDialog`, `ModuleCard` |
| `QtQuick/VirtualKeyboard/Styles/hai/` | estilo claro do teclado, nas cores da plataforma |

A QML recebe duas propriedades de contexto: `theme` (a paleta de
`ui/theme.py`, em camelCase: `theme.userBubble`) e `app` (o `AppController`
de `core/app.py`: módulos, aviso do menu, tela cheia, preferências do teclado).

## Modelo de execução

- **Um único event loop:** o do Qt, que também roda o asyncio (qasync).
  Slots chamados pela QML e corrotinas rodam na mesma thread, então não há
  filas entre threads, e uma tarefa nunca mexe numa tela que outra thread fechou.
- **Trabalho bloqueante fica fora do loop**, nas threads de cada serviço: rede
  do LLM (`run_in_executor`), Whisper e OpenCV (`asyncio.to_thread`), áudio do
  PortAudio (callback em thread C) e TTS (thread própria com fila).
- **Falhas globais:**
  - avisos da QML vão para o log (`engine.warnings`);
  - erro num evento da sessão do chat vai para o log e a tela continua;
  - falha ao abrir um módulo volta ao menu com aviso;
  - configuração ausente ou inválida vira aviso no menu em vez de derrubar a aplicação;
  - sem sessão gráfica (`$WAYLAND_DISPLAY` e `$DISPLAY` vazios), `main()`
    retorna 1 antes de criar a `QGuiApplication`, porque sem isso o Qt aborta o processo.

## Inicialização e encerramento

1. `load_config()` lê `config/settings.toml` e `config/secrets.toml`. Arquivo
   ausente ou inválido vira um texto em `problems`, nunca uma exceção.
2. `Services` cria o cliente LLM (se houver chave), o TTS e a câmera. Nenhum
   deles abre dispositivo: a câmera abre a cada foto e o Whisper só carrega na
   primeira chamada de `get_asr()`.
3. `configure_qt()` define o método de entrada (teclado da tela) e o estilo,
   antes da `QGuiApplication`.
4. `build_modules(services)` instancia os módulos. A construção não abre recursos.
5. `App.build()` carrega `Main.qml`; `App.run()` espera o pedido de parada e
   instala os handlers de SIGINT e SIGTERM.
6. Fechar a janela, Ctrl+C ou SIGTERM → `App.shutdown()`:
   - cancela as tarefas de navegação e sai do módulo ativo;
   - chama `close()` de cada módulo e `Services.close()` (para o TTS e corta o stream do LLM);
   - destrói o motor da QML antes dos objetos que ela lê.

   É idempotente.

## Navegação e ciclo de vida dos módulos

O contrato está em `modules/base.py`:

| Membro | Chamado quando | Responsabilidade |
|---|---|---|
| `id`, `title`, `summary` | montagem do menu | identificação e texto do cartão |
| `icon` (`icon.svg`), `page` (`Page.qml`) | montagem do menu / entrada | arquivos da pasta do módulo |
| `unavailable_reason()` | montagem do menu e toque no cartão | motivo legível para não abrir (ex.: sem chave da API), ou `None` |
| `enter(go_back)` | toque no cartão | adquire os recursos da atividade e devolve o controller da página |
| `exit()` | Voltar ou encerramento | cancela tarefas e timers e libera os recursos da atividade |
| `close()` | encerramento da aplicação | libera o que o módulo manteve entre entradas (normalmente nada) |

Regras aplicadas por `core/app.py`:

- Abrir e voltar passam por um `asyncio.Lock`: dois toques no cartão não abrem
  o módulo duas vezes, e não há dois módulos ativos.
- Entrada: `enter()` devolve o controller, e a App empilha a `Page.qml` do
  módulo com ele (`controller` na página).
- Saída: a página sai da pilha e o módulo libera os recursos em `exit()`. O
  controller ainda vive até a próxima navegação, porque a página o lê
  durante a animação de saída. Por isso todo slot ignora chamadas depois de
  `exit()`.
- Se `enter()` falhar, o app chama `exit()` mesmo assim (por isso `exit()` deve
  tolerar uma entrada incompleta) e mostra o aviso no menu.

Os testes de navegação repetida (`tests/test_app.py`) contam os itens das
telas, as tarefas asyncio, os microfones e as fotos em memória antes e
depois de várias idas e voltas em cada módulo.

## Padrões de interface compartilhados

| Peça | Onde | Regra |
|---|---|---|
| Paleta | `ui/theme.py` | todo par texto/fundo usado está em `CONTRAST_PAIRS`. `tests/test_theme.py` exige 4,5:1 para texto e 3:1 para contornos, anel de foco e botão desabilitado (WCAG 2.1 AA) |
| Botões | `Hai.HaiButton` | `kind`: `primary`/`danger`/`success` (preenchido, um por área), `secondary` (contorno), `ghost` (só texto: ← Menu, ⋯). No mínimo 48 × 48 px. Tocar não tira o foco do campo de texto (`Qt.TabFocus`), então o teclado não fecha ao tocar em Enviar; no Tab do teclado físico há anel de foco |
| Confirmação | `Hai.ConfirmDialog` | ações destrutivas (Nova conversa, sair com pergunta em edição). Escurece a tela; Esc ou toque fora cancelam |
| Aviso | `Hai.Toast` | no fluxo da tela, sem cobrir o conteúdo. Avisos somem em 5 s; erros ficam até o ✕, até a ação ("Tentar de novo") ou até a próxima atividade (quem decide é o controller) |
| Menu | `ui/qml/MenuPage.qml` | 1 módulo: cartão grande centralizado; 2 a 6: grade centralizada de até 3 colunas; mais de 6: a grade rola por arrasto; o motivo de indisponibilidade aparece curto no cartão |

Teclas globais: F11 alterna a tela cheia (`Main.qml`). Esc fica para os
módulos (no chat, cancela a operação em andamento).

`[display] open_single_module = true` faz `App.build()` abrir direto o único
módulo ativo, se ele estiver disponível; ← Menu continua levando ao menu.

## Teclado na tela

O Qt Virtual Keyboard é o método de entrada do próprio processo
(`configure_qt()`): tocar num campo abre o teclado embutido na janela
(`Keyboard.qml`), e a tela encolhe para o espaço de cima. Assim o teclado
nunca cobre o editor nem o botão Enviar.

- Layout pt-BR, com Ç e acentos ao segurar a vogal; maiúscula automática no
  começo da frase. Campos com `Qt.ImhDigitsOnly` (módulo de exemplo) abrem
  direto no layout numérico.
- Predição de palavras desligada (`Qt.ImhNoPredictiveText`): falta confirmar
  se há dicionário pt-BR no Pi.
- **Estilo claro "hai"** (`ui/qml/QtQuick/VirtualKeyboard/Styles/hai/`), nas
  cores da plataforma. O estilo padrão do Qt é escuro. A proporção (1024 × 270)
  deixa o editor e a barra de ações à vista numa tela de 1024 × 600.
- A sessão do sistema costuma exportar `QT_IM_MODULES` (no GNOME,
  `wayland;ibus`). `configure_qt()` sobrescreve `QT_IM_MODULE` e
  `QT_IM_MODULES`; sem as duas, o Qt carrega o IBus e o teclado nunca aparece.
- No Wayland, o Qt avisa no log que `qtvirtualkeyboard currently is not
  supported at client-side`, mas o teclado embutido funciona: medido e testado
  no GNOME (Wayland e XWayland). Falta confirmar no labwc do Pi.
- No chat, o menu ⋯ tem **Teclado na tela** (`app.keyboardEnabled`). Desligado,
  o painel não aparece e a tela fica inteira para quem usa teclado físico.
  Ligar de novo abre o teclado na hora. Vale até fechar o app.
- `[display] on_screen_keyboard = false` nem carrega o teclado; o método de
  entrada volta a ser o do sistema (IBus, teclas mortas pela tabela Compose).
- O teclado físico funciona com o virtual ativo. Ainda falta conferir as
  teclas mortas (´ + a) num teclado físico com o teclado virtual ligado.

Por que um teclado embutido e não o do sistema (squeekboard): em tela cheia,
um teclado do sistema sobrepõe a janela em vez de ela encolher, e a abertura
automática depende do compositor.

## Desempenho

Medido num PC com GNOME (Wayland), com o roteiro usado na versão em Tk.
Falta repetir no Raspberry Pi 5 (labwc).

| Operação | Tk (já otimizado) | Qt Quick |
|---|---|---|
| Menu (montar + 1º quadro) | 0,10 s | 0,55 s (inclui compilar a QML e carregar o teclado) |
| Abrir o chat | 0,27 s | 0,19 s |
| Tocar no editor → teclado desenhado | 19 ms | 27 ms (1ª vez), 12 ms depois |
| Resposta de 150 trechos (custo da tela) | 0,12 s | 0,02 s |

O que mantém a tela leve:

- **Streaming:** o controller agrupa os trechos em atualizações de no máximo
  uma a cada 50 ms (`_STREAM_PAINT_MS`). Cada uma muda só o papel `text` daquela
  linha do modelo (`ui/models.py`), e só aquele balão se redesenha.
- **Editor incremental** (`modules/chat/editor.py`): foto nova, fala transcrita
  ou rascunho devolvido trocam só o trecho do documento que mudou.
- **Whisper** pré-carregado ~1 s depois do menu aparecer, se algum módulo
  declara `uses_speech = True` (`[stt] preload = false` desliga).
- A QML compilada fica em cache em disco (`~/.cache/<app>/qmlcache`): a
  primeira abertura depois de editar a QML é mais lenta.

## Serviços compartilhados

| Serviço | Criado | Vida útil | Observações |
|---|---|---|---|
| `services.llm` (`api.llm_client.LLMClient`) | no início, se houver chave | toda a execução | uma sessão de chat por vez; `resetar_sessao()` descarta o histórico |
| `services.tts` (`tts.speaker.TTSSpeaker` ou `NullTTS`) | no início | toda a execução | thread com fila; `stop_speaking()` interrompe na hora |
| `services.camera` (`vision.camera.CameraCapture`) | no início, se `[camera] enabled` | toda a execução | abre o dispositivo só durante cada captura |
| `services.get_asr()` (`stt.whisper_engine.WhisperEngine`) | na primeira chamada | toda a execução | carregado uma vez em thread; chamadas simultâneas esperam o mesmo carregamento |
| `services.make_recorder()` (`stt.recorder.VoiceRecorder`) | por chamada | do módulo que pediu | o microfone não é compartilhado: quem abre fecha em `exit()` |

Voltar ao menu não recarrega o Whisper nem recria o cliente LLM. O que é
específico de uma atividade (microfone aberto, histórico da conversa, fotos)
pertence ao módulo. As fotos exibidas ficam em `ui/images.py` (memória do
processo) só enquanto a conversa existe: sair do módulo ou apagar a conversa as solta.

`Services` também guarda preferências de interface lidas da configuração, como
`on_screen_keyboard`, para os módulos não lerem o TOML diretamente.

## Dependências

`requirements.txt`:
- interface: `PySide6-Essentials` e `PySide6-Addons` (o Qt Virtual Keyboard
  vem no Addons; o WebEngine fica de fora) e `qasync`;
- o resto: PyAudio, faster-whisper e numpy, opencv-python-headless,
  google-genai e pyttsx3.

Pacotes de sistema: `portaudio19-dev`, `alsa-utils` (`aplay`, usado pelo
Piper) e `espeak-ng`. As bibliotecas que o Qt usa do sistema (EGL, xkbcommon,
fontconfig, Wayland) já vêm no Pi OS com área de trabalho.

Licenças: o Qt é LGPLv3, mas o **Qt Virtual Keyboard é GPLv3**. O código do
projeto continua MIT. Distribuir o app junto com o teclado (uma imagem do Pi,
por exemplo) segue a GPLv3 no conjunto.
