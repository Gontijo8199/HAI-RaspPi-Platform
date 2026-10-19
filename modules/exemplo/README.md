# Módulo de exemplo

Referência mínima de um módulo da plataforma. A atividade é simples de
propósito: o aluno digita um número inteiro e o módulo mostra seus divisores,
se ele é primo e a fatoração em primos. Não usa rede, credenciais, câmera nem
microfone, então abre sempre.

Vem **desativado** no menu. Para vê-lo, ponha no `config/settings.toml`:

```toml
[modules]
exemplo = true
```

Ativo, ele aparece como **Módulo de exemplo**. Não é uma ferramenta de produção.

## Estrutura

| Arquivo | Papel | Depende do Qt |
|---|---|---|
| `logic.py` | `parse_number` (validação), `divisors`, `factorize`, `analyze` e `describe` (texto para a tela); `InvalidInput` carrega a mensagem para o aluno | não |
| `controller.py` (`ExampleController`) | propriedades `verdict`, `details`, `error` e os slots `check(texto)`, `clear()`, `back()`; chama `analyze()` | sim (`QObject`) |
| `Page.qml` | campo, botões Verificar e Limpar e área de resultado; só lê o controller e chama os slots | sim (QML) |
| `icon.svg` | ícone do cartão do menu | — |
| `module.py` (`ExampleModule`) | `id`, `title`, `summary` e ciclo de vida | não |
| `__init__.py` | exporta `ExampleModule` | — |

O registro fica em `modules/__init__.py`:

```python
REGISTRY = {
    "chat": (_chat, True),
    "exemplo": (_exemplo, False),  # False = desativado por padrão
}
```

## Fluxo

1. Toque no cartão → `App.enter_module()` chama `ExampleModule.enter(go_back)`,
   que cria o `ExampleController`; a App empilha `Page.qml` com ele.
2. O campo já recebe o foco. Ao tocar nele, o teclado da tela abre no layout
   numérico (`inputMethodHints: Qt.ImhDigitsOnly`); o teclado físico também serve.
3. **Verificar**, Enter ou ⏎ do teclado da tela → `controller.check(texto)` →
   `logic.analyze(texto)`.
4. Entrada válida: `describe()` gera o veredito e os detalhes. Inválida:
   `InvalidInput` traz o motivo ("Digite só algarismos…", "O zero é divisível
   por todos…"), `check()` devolve `False` e a página seleciona o texto do
   campo para ser corrigido.
5. **← Menu** → `controller.back()` → `go_back()` → `App.leave_module()`: a
   página sai da pilha e `ExampleModule.exit()` fecha o controller, que passa a
   ignorar qualquer chamada atrasada da página.

Entradas aceitas: inteiros de 1 a 1.000.000, só algarismos ASCII, com espaços
em volta ignorados. O limite mantém a lista de divisores legível na tela.

## Recursos

O único recurso por entrada é o controller, e ele não tem timers nem tarefas.
Um módulo que use serviços (LLM, câmera, microfone) deve, além disso, guardar
as tarefas assíncronas e cancelá-las em `exit()`, como `modules/chat/module.py`.

## Testes

- `tests/test_exemplo_logic.py`: divisores, fatoração, veredito e cada tipo de
  entrada inválida, sem Qt.
- `tests/test_app.py::test_modulo_de_exemplo_valida_calcula_e_volta`: abre pelo
  `App`, digita uma entrada inválida e depois "28" com Enter, confere o
  resultado e volta ao menu sem sobrar itens na tela.
- `tests/test_keyboard.py::test_campo_numerico_abre_o_layout_de_numeros`: o
  teclado da tela abre nos números e digita no campo.
- `tests/test_app.py::test_navegacao_repetida_nao_acumula_recursos`: várias
  idas e voltas sem sobrar itens nem tarefas.

## Como usar de base

Copie a pasta com outro nome, troque a regra em `logic.py`, o estado em
`controller.py`, a tela em `Page.qml` e o ícone, ajuste `id`, `title` e
`summary` em `module.py` e registre a classe em `REGISTRY`. Passo a passo e
convenções em [docs/development.md](../../docs/development.md#criar-um-módulo).
