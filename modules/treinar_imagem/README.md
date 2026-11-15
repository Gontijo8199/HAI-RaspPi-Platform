# Treinar reconhecedor de imagem

Versão para a plataforma do quadradinho `treinar-imagem.html` da POC. O aluno
cria classes ("Gato", "Caneca"…) e tira fotos de cada uma pela webcam.
Ao tocar em **Treinar**, o computador passa a reconhecer as classes, e
**Testar** tira uma foto nova e mostra a porcentagem de cada classe.

À direita fica a prévia ao vivo da câmera (≈10 quadros/s, `LiveCamera` em
`vision/camera.py`). **+** e **Testar** usam o quadro que está na tela, então
o aluno vê o que vai fotografar. Se a prévia não abrir (câmera ocupada, por
exemplo), o módulo avisa e cada toque tira uma foto com `CameraCapture.capture()`.

## Como funciona

- `embedder.py`: a MobileNetV2 (ONNX, no `onnxruntime`) transforma cada foto
  num vetor de 1000 números com norma 1. O modelo roda localmente, sem rede.
- `logic.py`: um KNN. "Treinar" só guarda os vetores. Prever é votar entre as
  k fotos mais parecidas (cosseno), com k ≤ 3 e nunca maior que a menor classe;
  com 1 foto por classe, k = 1. As confianças somam 1.
- `controller.py` (`TrainerController`): a lista `classes` (nome, fotos,
  confiança, vencedora), `status`, `busy`, `trained`, `photo` e os slots
  `newClass()`, `rename(linha, nome)`, `addPhoto(linha)`, `train()`, `test()`
  e `back()`.
- `module.py` (`TrainerModule`): carrega o extrator na primeira foto (numa
  thread) e o mantém entre as entradas. Fica indisponível no menu se a câmera
  estiver desativada.

## Modelo

O modelo não é versionado. Baixe uma vez (≈14 MB, precisa de internet):

```bash
python -m modules.treinar_imagem.embedder --download
```

Ele fica em `models/mobilenetv2.onnx`. A imagem Docker já o baixa no build.
Sem o modelo, o módulo abre normalmente, mas a primeira foto mostra o comando
acima na tela.

## Privacidade

Fotos, vetores e classes ficam só na memória e somem ao voltar ao menu. A
câmera fica aberta só enquanto o módulo está na tela.

## Testes

- `tests/test_treinar_imagem_logic.py`: KNN e a regra de "pode treinar".
- `tests/test_treinar_imagem_controller.py`: fluxo completo com câmera e
  extrator simulados, erros e chamadas depois da saída.
- `tests/test_treinar_imagem_embedder.py`: o modelo de verdade (pulado se não
  foi baixado).
- `tests/test_app.py::test_modulos_de_imagem_funcionam_e_nao_deixam_sobras`.
