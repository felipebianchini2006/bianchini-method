# Runners por plataforma

Escolher a menor combinação que prova o contrato. Reutilizar comandos, testes e harnesses do repositório.

| Plataforma | Runner preferido | Evidência mínima |
|---|---|---|
| Web | Browser plugin, quando disponível; senão Playwright existente | Build real, interação, console, rede, desktop e viewport móvel |
| Android | `android-emulator-qa`, quando disponível; senão ADB | Árvore de UI, screenshots e logcat |
| iOS | `ios-debugger-agent` ou equivalente de Simulator | Descrição/labels da UI, screenshots e logs |
| Android TV | ADB com keyevents | Foco, navegação por controle, screenshots e logs |

Em Flutter ou React Native, usar Maestro somente se já existir ou reduzir claramente o trabalho. Android TV não é touchscreen. Computer Use é último recurso.

Com código compartilhado, escolher plataforma primária pelo contrato, uso, risco ou mudança do RC: jornada completa nela e smoke crítico na secundária. Cobrir ambas por completo quando existir comportamento nativo ou diferença conhecida. Registrar alvo, versão e runner realmente executados.
