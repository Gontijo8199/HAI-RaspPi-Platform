# HAI — Human-AI Interaction Platform

Dispositivo embarcado para letramento em IA. Captura prompts de voz, transcreve localmente via `whisper.cpp` e envia o texto a um LLM remoto via API, exibindo a resposta em display físico.

**Hardware:** Raspberry Pi 5 -  Raspberry Pi OS Lite

## Arquitetura

```
[voz] → [whisper.cpp] → [LLM API] → [display]
          STT local       remoto
```

## Estrutura

```
.
├── stt/       # captura de áudio e integração whisper.cpp
├── api/       # cliente da API do LLM
├── display/   # driver e renderização no display
├── core/      # controle do pipeline
└── config/    # configurações do dispositivo e modelo
```

## Status

Em desenvolvimento, módulos principais ainda em construção.

## Licença

A definir.
