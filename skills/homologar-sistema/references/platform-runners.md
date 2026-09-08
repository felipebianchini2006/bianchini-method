# Runners por plataforma

Leia somente a linha da plataforma homologada. Descubra primeiro o que o projeto e o host já oferecem.

| Superfície | Preferência | Evidência útil |
|---|---|---|
| Web | browser interno visível do harness; suíte E2E existente como complemento | screenshots, trace e console/rede |
| API | cliente ou testes de contrato do projeto | request, response e efeitos sanitizados |
| CLI | processo real em diretório temporário | stdout, stderr, exit code e filesystem |
| Android/iOS | emulador, simulador ou dispositivo de teste | captura, versão e logs nativos |
| Desktop | aplicativo empacotado | SO/build, jornada e capturas |
| Biblioteca | consumidor mínimo real | instalação/importação, saída e versão |
| Dados/migração | banco ou pipeline descartável | estado anterior/posterior e recuperação |
| Infra/cloud | validate/plan/dry-run | plano sanitizado; aplicação só autorizada |

Espere condições observáveis. Evite sleeps arbitrários. Se a plataforma obrigatória não puder ser operada por nenhuma ferramenta disponível, registre o bloqueio; não a reclassifique como não aplicável.
