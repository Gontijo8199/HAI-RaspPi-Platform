# Módulo "Conversar com a IA"

O aluno escreve uma pergunta, fala trechos e põe fotos no meio do texto, na
ordem que quiser, e envia tudo de uma vez a um LLM remoto. A resposta aparece
em Markdown enquanto chega e é lida em voz alta, frase a frase.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `module.py` (`ChatModule`) | registro no menu e ciclo de vida: cria sessão, gravador e controller em `enter()`, libera tudo em `exit()` |
| `session.py` (`ChatSession`) | toda a lógica, sem interface: rascunho ordenado, uma atividade por vez, envio multimodal, streaming para tela e TTS, cancelamento, nova conversa |
| `controller.py` (`ChatController`) | implementa `ChatListener` e expõe à tela o estado pronto (rótulos e cores dos botões, resumo, avisos, modelo das mensagens) e as ações em slots; agrupa o streaming |
| `editor.py` (`RichEditor`) | o editor: o `QTextDocument` do `TextArea`, com as fotos como imagens embutidas; serializa na ordem visual e redesenha só o trecho que mudou |
| `Page.qml` | a tela (cabeçalho, histórico, aviso, editor, botões, menu ⋯, prévia da foto, diálogos); só lê o controller e chama os slots |
| `icon.svg` | ícone do cartão do menu |

## Tela

```
[← Menu]  Conversar com a IA                                         [ ⋯ ]
┌ histórico: aluno à direita, IA à esquerda ─────────────────────────────┐
│                                                   [ ↓ Nova resposta ]  │
└────────────────────────────────────────────────────────────────────────┘
⚠ aviso ou erro                                     [Tentar de novo] [✕]
┌ Olha este exercício: [foto 1] e este: [foto 2] qual está certo?▌ ─────┐
│ [● Falar] [Foto]                  2 fotos · 9 palavras     [Enviar ➤]  │
└────────────────────────────────────────────────────────────────────────┘
[ teclado na tela, quando aberto: o histórico vira uma prévia do fim ]
```

- **Editor:** tocar nele (ou na dica "Escreva sua pergunta…") abre o teclado da
  tela. As fotos e as falas entram **no ponto do cursor**, e a ordem enviada é a
  ordem que se vê. ⌫ apaga uma foto como um caractere; tocar na miniatura abre
  a foto em tamanho maior, com **Remover foto**. Colar cola só o texto.
- **Falar:** um toque começa a gravar e outro termina ("■ Parar gravação 0:07");
  segurar e soltar também funciona. Corte automático em 60 s. Enquanto isso, um
  rótulo "gravando…" e depois "transcrevendo…" marca onde o texto vai entrar.
  Se o microfone não captar som (mudo, desligado, dispositivo errado), o Whisper
  nem é chamado e um aviso explica o problema. Se nada for reconhecido, também
  só aparece um aviso: **nunca entra texto de erro na pergunta**.
- **Foto:** captura um quadro da webcam e mostra a prévia: **Usar foto**,
  **Tirar outra** (no mesmo lugar) ou **Cancelar**. São até 6 fotos por pergunta.
- **Enviar** (ou **Ctrl+Enter**): só fica ativo com conteúdo. Durante a
  resposta, vira **■ Parar resposta** no mesmo lugar, o que impede o envio
  duplicado; durante a leitura em voz alta, vira **■ Parar leitura**.
  **Enter quebra a linha**, no teclado físico e no da tela.
- **Esc** (teclado físico): cancela a gravação, a foto, a resposta ou a leitura.
- **⋯:** "Ler respostas em voz alta" (✓ quando ligado), "Teclado na tela"
  (✓ quando ligado; desligado, o teclado da tela não aparece e a tela fica
  inteira para o teclado físico; ligar abre o teclado na hora) e
  **Nova conversa…**, que pede confirmação.
- **← Menu:** sai direto; com pergunta em edição ou algo em andamento, pergunta
  antes ("Sair da conversa?"), porque sair apaga a conversa.

### Estados

Não há linha de status: cada estado aparece onde o aluno está olhando.

| Estado | Onde aparece |
|---|---|
| Preparando a voz | botão "Preparando microfone…" (desativado) |
| Gravando / transcrevendo | botão Falar com o tempo; rótulo no editor, na posição do texto |
| Tirando a foto | botão "Tirando foto…"; espaço reservado no editor |
| Aguardando a IA | balão da IA com "●○○ Pensando… 0:12" animado |
| Respondendo | texto chegando no balão; botão "■ Parar resposta" |
| Lendo em voz alta | botão "■ Parar leitura"; escrever ou gravar também interrompe |
| Erro de envio | balão com "⚠ motivo" e **↻ Tentar de novo**; a pergunta volta ao editor; o aviso fica até ser dispensado |
| Erro de câmera ou microfone | aviso persistente com **Tentar de novo** quando faz sentido |
| Microfone sem sinal / nada reconhecido | aviso persistente; o editor não muda |

Durante a espera, o editor continua livre: o aluno pode escrever a próxima
pergunta. Se a resposta falhar, a pergunta anterior volta antes do que já foi
escrito.

### Espaço vertical

O cabeçalho (≈ 56 px), a barra de ações e o aviso têm altura fixa. O editor
cresce com o conteúdo até deixar 160 px para o histórico e depois rola por
dentro.

Com o teclado aberto sobram ≈ 330 px em 1024 × 600:
- o editor fica com o que o conteúdo pede, até 120 px (uma linha de miniaturas);
- o histórico vira uma **prévia** com o fim da conversa (a última resposta),
  com o espaço que sobra, até 132 px, e some se não couber nem uma linha;
- **▴ Ver tudo** na prévia fecha o teclado.

Ao enviar, o teclado fecha para a resposta aparecer. A rolagem do histórico
é independente da do editor. Se o aluno rolou para cima e chega texto novo,
aparece **↓ Nova resposta**, e a tela não é puxada para baixo.

## Fluxo de uma pergunta

```
Falar → PortAudio → Whisper (local) ──┐
teclado (físico ou da tela) ──────────┼─► editor ─► Composer.serialize()
Foto → OpenCV → prévia → JPEG ────────┘              │  [texto, foto, texto…]
                                       session.replace_draft() ─► Enviar
       LLMClient.send_parts_stream (1 requisição, streaming)
            ├─► balão da IA, Markdown a cada trecho
            └─► SentenceChunker → TTSSpeaker, frase a frase
```

Contrato editor ↔ sessão:
- `ChatSession.draft` (lista de `DraftBlock`) é a fonte da verdade.
- A cada edição, o controller chama `replace_draft(editor.items())`, com textos e ids de fotos na ordem visual.
- Foto e voz recebem o índice do cursor (`take_photo(i)`, `begin_recording(i)`) e reservam a posição com um bloco `pending`.
- Quando a sessão muda o rascunho (foto pronta, transcrição, rascunho devolvido após erro), ela emite `draft_changed(blocos, foco)`: o editor troca só o trecho que mudou e o cursor vai para depois do bloco novo.

## Dependências

| Serviço (`core/services.py`) | Uso | Sem ele |
|---|---|---|
| `llm` | envio e streaming das respostas | o módulo fica indisponível no menu, com o motivo no cartão |
| `get_asr()` (Whisper) | transcrição | botão Falar mostra "Voz indisponível"; texto e foto continuam |
| `make_recorder()` (PyAudio) | microfone, aberto só dentro do módulo | idem |
| `camera` | fotos | botão Foto não aparece (`[camera] enabled = false`) ou mostra o erro |
| `tts` | leitura das respostas | o item "Ler respostas" some do menu ⋯ (`--no-tts`) |

Configuração relevante: `[api] model` e `timeout_s`, `[stt]`, `[tts]`,
`[camera]` e `[display] on_screen_keyboard`. A chave fica em
`config/secrets.toml`.

## Ciclo de vida e recursos

- `enter()`: cria a `ChatSession` (que recria a sessão do LLM) e o
  `ChatController`, abre o
  microfone **pausado** no PortAudio e começa a carregar o Whisper em segundo
  plano, se ainda não estiver carregado. Normalmente ele já está: o módulo
  declara `uses_speech = True`, e a App o pré-carrega enquanto o menu está aberto.
- `exit()`: cancela as tarefas da tela, chama `session.stop()` (cancela
  atividade, stream e fala, fecha o microfone, recria a sessão do LLM e apaga
  mensagens, rascunho e fotos) e `controller.close()`. Este último para os
  timers (aviso, streaming, limite da gravação), solta as fotos da memória de
  imagens (`ui/images.py`) e passa a ignorar chamadas da página, que ainda
  anima a saída.
- Cada tarefa da sessão guarda a "época" em que começou. `stop()` e
  `new_conversation()` avançam a época, então um resultado atrasado
  (transcrição, foto, trecho do LLM) é descartado e não chega a uma tela fechada
  nem a uma conversa nova.

## Privacidade

Nada da conversa vai para o disco. O microfone só captura enquanto a gravação
está ativa. Os logs registram tipos de erro e tamanhos, nunca o conteúdo; o
detalhe técnico de uma falha de câmera vai para o log, e a tela mostra só a
frase para o aluno. `[camera] save_dir` (vazio por padrão) é a única exceção,
para depuração.

## Testes

- `tests/test_chat_session.py`: lógica, com dublês de LLM, gravador, Whisper,
  câmera e TTS, incluindo `replace_draft`, inserção no índice, espaço reservado
  da foto e limite de fotos.
- `tests/test_chat_controller.py`: o que a tela mostra e faz, sem QML:
  - rótulos e habilitado dos botões;
  - foto no cursor, tirar outra e remover;
  - voz por toque, por segurar e com microfone mudo; limite da gravação;
  - Enviar ↔ Parar sem envio duplicado;
  - streaming agrupado (150 trechos, menos de 20 atualizações);
  - erros persistentes e "Tentar de novo" só no último;
  - sair e nova conversa; nada depois de fechar.
- `tests/test_chat_editor.py`: o editor com fotos embutidas (ordem visual, ⌫,
  colar, redesenho que não refaz as fotos que já estavam).
- `tests/test_chat_page.py`: a tela em QML:
  - alvos de 48 px em 1024 × 600;
  - Markdown, Ctrl+Enter e Esc;
  - prévia da foto e toque na miniatura;
  - aviso com ação, confirmações, menu ⋯;
  - "↓ Nova resposta".
- `tests/test_keyboard.py`: o teclado da tela no chat (abre, encolhe a tela,
  prévia do histórico, escreve, desliga e liga pelo menu ⋯).
- `tests/test_app.py`: navegação repetida sem vazamento de itens, tarefas,
  microfones ou fotos.
- `tests/test_llm_client.py`: ordem das partes, streaming, cancelamento, erros.

## Limitações

- O tempo de resposta depende do modelo remoto; acima de `[api] timeout_s`
  aparece erro e a pergunta volta ao editor.
- Fotos só da webcam; não há anexo de arquivos.
- O Ctrl+Z não desfaz um redesenho feito pela sessão (foto nova, transcrição):
  o histórico de desfazer recomeça nesses pontos.
- Os botões têm `Accessible.name`, mas a interface não foi testada com um
  leitor de tela (Orca); a leitura em voz alta das respostas é o recurso de
  áudio garantido.
- Se o LLM devolver uma resposta vazia, a pergunta pode ter ficado no
  histórico da sessão remota, e reenviá-la a repete.
