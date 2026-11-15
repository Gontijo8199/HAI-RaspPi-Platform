# Gerar imagem

Versão para a plataforma do quadradinho `gerar-imagem.html` da POC. O aluno
descreve uma cena e a IA (Gemini) desenha a imagem.

Usa o cliente LLM compartilhado (`LLMClient.generate_image`) e a mesma chave
do chat (`[api] key` em `config/secrets.toml`). O modelo vem de `[api]
image_model` (padrão `gemini-2.5-flash-image`). Sem chave, o cartão aparece
indisponível no menu.

## Estrutura

- `controller.py` (`ImageGenController`): `status`, `error`, `busy`, `image`
  e os slots `generate(texto)` e `back()`. Uma descrição vazia é recusada na
  tela e não chega à API.
- `module.py` (`ImageGenModule`): guarda a tarefa da geração e a cancela em
  `exit()`. O cliente assíncrono do genai cancela a requisição.
- `Page.qml`: campo de descrição, botão Gerar, status e a imagem.

A espera máxima é `IMAGE_TIMEOUT_S` (120 s), em `api/llm_client.py`. Erros de
rede ou da API viram mensagens legíveis (`describe_error`).

## Privacidade

A imagem fica só na memória e some ao voltar ao menu. O botão Salvar da POC
não foi trazido: a plataforma não grava nada em disco.

## Testes

- `tests/test_gerar_imagem_controller.py`
- `tests/test_llm_client.py::test_generate_image_*`
- `tests/test_app.py::test_modulos_de_imagem_funcionam_e_nao_deixam_sobras`
