# Seleção de runners por plataforma

Escolher ferramenta já configurada no projeto antes de adicionar outra. A tabela orienta descoberta; não é uma lista de dependências obrigatórias.

| Plataforma/superfície | Preferência estruturada | Fallback verificável | Evidência mínima |
|---|---|---|---|
| Web | suíte E2E existente, Playwright, Cypress | browser control/manual guiado | relatório + screenshot de marcos/falhas |
| API HTTP | testes de contrato/integração, cliente do projeto | `curl`/cliente equivalente com fixture | request/response sanitizados + status |
| CLI | harness de processo/subprocess | shell em diretório temporário | stdout/stderr, exit code e efeitos no filesystem |
| Android | testes instrumentados, Maestro, ADB/emulador | interação manual no emulador | versão, dispositivo, screenshot/logcat sanitizado |
| iOS | XCTest/XCUITest, Maestro, Simulator | interação manual no Simulator | versão, dispositivo, screenshot/log sanitizado |
| Desktop | runner nativo/E2E do framework | sessão manual isolada | SO/build, passos e capturas |
| Biblioteca/SDK | consumer fixture + testes de contrato | projeto mínimo temporário | instalação/importação, saída e versão |
| Banco/migração | banco descartável + ferramenta nativa | dry-run e cópia sanitizada | schema antes/depois, contagens e rollback/forward-fix |
| Fila/job | harness de integração com clock/fila controlada | worker local e mensagens sintéticas | input, estado final, retries/erro |
| Infra/cloud | validate/plan/policy da ferramenta | dry-run do provedor | plano sanitizado; aplicação só autorizada |
| Firmware/IoT | simulador/HIL existente | dispositivo de teste isolado | firmware/hardware, sinais e logs |
| Dados/ML | pipeline de avaliação versionado | amostra congelada local | dataset/version, métricas, tolerâncias e custo |

## Regras de escolha

1. Usar o runner que exercita a superfície mais próxima do usuário sem sacrificar determinismo.
2. Não substituir execução nativa por teste de unidade quando o risco está na plataforma.
3. Código compartilhado permite fluxo completo na plataforma primária e smoke na secundária somente se não houver API nativa, divergência conhecida ou requisito explícito de paridade completa.
4. Registre versão do runner, plataforma e RC. Resultado sem esses vínculos não prova a entrega.
5. Para UI, seletores devem expressar papel, nome acessível ou identificador estável; coordenadas são último fallback.
6. Reduza flake esperando condições observáveis, nunca com sleeps arbitrários.

## Plataforma primária

Escolha pela maior cobertura de comportamento e uso contratado, não pela conveniência da máquina. Registre a justificativa. Se a plataforma primária não estiver disponível, a homologação não pode simplesmente promovê-la a “não aplicável”.
