#!/usr/bin/env python3
"""Aplica a integração v3.1 sobre o CLI e a documentação existentes."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    if new in content:
        return
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: esperado um match, encontrados {count}: {old[:80]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def patch_cli() -> None:
    path = ROOT / "skills/_shared/scripts/bm.py"
    replace_once(
        path,
        "from typing import Any\n\n\nEXIT_INVALID = 2",
        "from typing import Any\n\n"
        "from bm_context_efficiency import (\n"
        "    ContextEfficiencyError,\n"
        "    quality_v2_unit_contract_errors,\n"
        "    verify_mutation_evidence,\n"
        "    write_hydrated_task_brief,\n"
        "    write_spec_diff,\n"
        ")\n\n\nEXIT_INVALID = 2",
    )
    replace_once(
        path,
        "    readiness_summary: dict[str, Any] | None = None\n    if quality_v2:\n",
        "    if quality_v2:\n"
        "        errors.extend(quality_v2_unit_contract_errors(state, root))\n\n"
        "    readiness_summary: dict[str, Any] | None = None\n"
        "    if quality_v2:\n",
    )
    replace_once(
        path,
        "    brief.add_argument(\"--output\", type=Path, required=True)\n\n"
        "    report = commands.add_parser(\"report\")",
        "    brief.add_argument(\"--output\", type=Path, required=True)\n"
        "    brief.add_argument(\"--state\", type=Path)\n"
        "    brief.add_argument(\"--root\", type=Path)\n"
        "    brief.add_argument(\"--hydrate-context\", action=\"store_true\")\n\n"
        "    spec_diff = commands.add_parser(\"spec-diff\")\n"
        "    spec_diff.add_argument(\"--base\", type=Path, required=True)\n"
        "    spec_diff.add_argument(\"--target\", type=Path, required=True)\n"
        "    spec_diff.add_argument(\"--output\", type=Path, required=True)\n\n"
        "    mutation = commands.add_parser(\"mutation-evidence\")\n"
        "    mutation.add_argument(\"action\", choices=[\"verify\"])\n"
        "    mutation.add_argument(\"--state\", type=Path, required=True)\n"
        "    mutation.add_argument(\"--root\", type=Path, required=True)\n"
        "    mutation.add_argument(\"--plan\", required=True)\n"
        "    mutation.add_argument(\"--risk-seam\", required=True)\n"
        "    mutation.add_argument(\"--tool\", required=True)\n"
        "    mutation.add_argument(\"--command\", required=True)\n"
        "    mutation.add_argument(\"--report\", type=Path, required=True)\n"
        "    mutation.add_argument(\"--output\", type=Path, required=True)\n\n"
        "    report = commands.add_parser(\"report\")",
    )
    replace_once(
        path,
        "        elif args.command == \"task-brief\":\n"
        "            emit(write_task_brief(args.plan, args.task, args.tasks, args.group, args.output))\n"
        "        elif args.command == \"report\":",
        "        elif args.command == \"task-brief\":\n"
        "            if args.hydrate_context:\n"
        "                if args.state is None or args.root is None:\n"
        "                    raise BMError(\n"
        "                        \"task-brief --hydrate-context exige --state e --root\"\n"
        "                    )\n"
        "                validate_state(args.state)\n"
        "                emit(\n"
        "                    write_hydrated_task_brief(\n"
        "                        plan=args.plan,\n"
        "                        task=args.task,\n"
        "                        tasks=args.tasks,\n"
        "                        group=args.group,\n"
        "                        state_path=args.state,\n"
        "                        root=args.root,\n"
        "                        output=args.output,\n"
        "                    )\n"
        "                )\n"
        "            else:\n"
        "                emit(\n"
        "                    write_task_brief(\n"
        "                        args.plan, args.task, args.tasks, args.group, args.output\n"
        "                    )\n"
        "                )\n"
        "        elif args.command == \"spec-diff\":\n"
        "            emit(write_spec_diff(args.base, args.target, args.output))\n"
        "        elif args.command == \"mutation-evidence\":\n"
        "            validate_state(args.state)\n"
        "            emit(\n"
        "                verify_mutation_evidence(\n"
        "                    state_path=args.state,\n"
        "                    root=args.root,\n"
        "                    plan_id=args.plan,\n"
        "                    risk_seam=args.risk_seam,\n"
        "                    tool=args.tool,\n"
        "                    command=args.command,\n"
        "                    report_path=args.report,\n"
        "                    output=args.output,\n"
        "                )\n"
        "            )\n"
        "        elif args.command == \"report\":",
    )
    replace_once(
        path,
        "    except BMError as error:\n"
        "        print(str(error), file=sys.stderr)\n"
        "        return error.exit_code\n",
        "    except ContextEfficiencyError as error:\n"
        "        print(str(error), file=sys.stderr)\n"
        "        return error.exit_code\n"
        "    except BMError as error:\n"
        "        print(str(error), file=sys.stderr)\n"
        "        return error.exit_code\n",
    )


def patch_entrypoint() -> None:
    path = ROOT / "scripts/bm.py"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Entry point de desenvolvimento para o CLI empacotado do Bianchini Method.\"\"\"\n\n"
        "from pathlib import Path\n"
        "import runpy\n"
        "import sys\n\n\n"
        "TARGET = (\n"
        "    Path(__file__).resolve().parents[1]\n"
        "    / \"skills\"\n"
        "    / \"_shared\"\n"
        "    / \"scripts\"\n"
        "    / \"bm.py\"\n"
        ")\n"
        "sys.path.insert(0, str(TARGET.parent))\n"
        "runpy.run_path(TARGET, run_name=\"__main__\")\n",
        encoding="utf-8",
    )


def patch_readme() -> None:
    path = ROOT / "README.md"
    replace_once(
        path,
        "# Bianchini Method v3.0 — Planning Stability",
        "# Bianchini Method v3.1 — Context Efficiency",
    )
    replace_once(
        path,
        "`v3.0` é a versão do pacote.",
        "`v3.1` é a versão do pacote.",
    )
    replace_once(
        path,
        "change-policy  cycle-close  snapshot  policy  workspace(create|check|locate|resume)\n"
        "repo-hygiene(check|migrate)  task-brief  report  review-package\n"
        "checkpoint  proof-map  telemetry  status",
        "change-policy  cycle-close  snapshot  policy  workspace(create|check|locate|resume)\n"
        "repo-hygiene(check|migrate)  task-brief  spec-diff  mutation-evidence\n"
        "report  review-package  checkpoint  proof-map  telemetry  status",
    )
    marker = "## Homologação e manual\n"
    section = (
        "## Eficiência de contexto\n\n"
        "Unidades `quality_version: 2` devem declarar `Change` e `Readiness refs`. "
        "O `planning-audit` valida a categoria, a existência dos IDs e se cada referência "
        "realmente aponta para o plano correspondente.\n\n"
        "`task-brief --hydrate-context` produz em `.superpowers/` uma projeção derivada com "
        "digest aprovado, unidade, readiness citado, seções exatas da spec, `verification.fast` "
        "e final do ledger. O arquivo não é fonte de verdade e pode ser regenerado.\n\n"
        "`spec-diff` compara requisitos com IDs estáveis e gera uma visão `ADDED / MODIFIED / REMOVED` "
        "sem substituir as specs completas. `mutation-evidence verify` vincula o relatório ao HEAD ou RC, "
        "ignora score global e bloqueia somente lacunas não classificadas ou survivors que alterem "
        "comportamento aprovado alto/crítico.\n\n"
    )
    content = path.read_text(encoding="utf-8")
    if section not in content:
        if marker not in content:
            raise RuntimeError("README: marcador de homologação ausente")
        path.write_text(content.replace(marker, section + marker, 1), encoding="utf-8")


def patch_changelog() -> None:
    path = ROOT / "CHANGELOG.md"
    content = path.read_text(encoding="utf-8")
    section = (
        "## 3.1.0 - Context Efficiency\n\n"
        "- torna `Change` e `Readiness refs` campos determinísticos das unidades quality v2;\n"
        "- valida categoria de mudança, existência dos IDs e destino real de cada referência;\n"
        "- adiciona `task-brief --hydrate-context` como projeção compacta e descartável em `.superpowers/`;\n"
        "- adiciona `spec-diff` derivado por IDs estáveis com ADDED, MODIFIED e REMOVED;\n"
        "- adiciona `mutation-evidence verify` ligado ao HEAD/RC, sem gate por score global;\n"
        "- adiciona CI versionada com a suíte fragmentada e validação do entrypoint.\n\n"
    )
    if section not in content:
        path.write_text(content.replace("# Changelog\n\n", "# Changelog\n\n" + section, 1), encoding="utf-8")


def patch_contract() -> None:
    path = ROOT / "skills/_shared/METHOD_CONTRACT.md"
    marker = "## Fontes de verdade e segurança\n"
    section = (
        "## Projeções de eficiência de contexto\n\n"
        "Em `planning.quality_version: 2`, cada unidade declara `Change` e `Readiness refs`. "
        "O audit bloqueia categoria desconhecida, ID inexistente e referência cujo `destinations` "
        "não inclua o plano da unidade. Pacotes quality v1 permanecem compatíveis.\n\n"
        "Durante a execução, `task-brief --hydrate-context --state <state> --root <repo>` grava somente "
        "sob `.superpowers/` uma projeção do digest, unidade, itens readiness citados, seções exatas da spec, "
        "comandos rápidos e final do ledger. Essa projeção é regenerável, não entra no snapshot e nunca vence "
        "as fontes canônicas.\n\n"
        "`spec-diff` exige IDs estáveis em headings e deriva ADDED, MODIFIED e REMOVED entre a spec atual e "
        "a spec futura completa. `mutation-evidence verify` exige revisão correspondente ao HEAD ou fingerprint "
        "do RC; survivor sem classificação bloqueia, equivalente/inalcançável recebe justificativa e apenas "
        "lacuna que altera comportamento aprovado alto/crítico reprova. Percentual global não decide o gate.\n\n"
    )
    content = path.read_text(encoding="utf-8")
    if section not in content:
        if marker not in content:
            raise RuntimeError("METHOD_CONTRACT: marcador ausente")
        path.write_text(content.replace(marker, section + marker, 1), encoding="utf-8")


def patch_skills() -> None:
    planning = ROOT / "skills/sdd-planning/SKILL.md"
    replace_once(
        planning,
        "Não usar cobertura ou mutation score global. Gate indispensável indisponível é bloqueio.\n",
        "Não usar cobertura ou mutation score global. Gate indispensável indisponível é bloqueio. "
        "Em quality v2, `planning-audit` exige `Change` conhecido e `Readiness refs` existentes e destinados ao plano.\n",
    )
    execution = ROOT / "skills/executar-plano/SKILL.md"
    replace_once(
        execution,
        "- `task-brief` por grupo, slice ou tarefa;\n",
        "- `task-brief` por grupo, slice ou tarefa; usar `--hydrate-context --state <state> --root <repo>` "
        "para carregar somente readiness, specs, gates e ledger referenciados;\n",
    )
    replace_once(
        execution,
        "No gate do plano, executar suítes afetadas, regressão do plano, E2E crítico e mutação seletiva exigida. No release, executar os comandos completos aprovados. Não perseguir cobertura ou mutation score global.\n",
        "No gate do plano, executar suítes afetadas, regressão do plano, E2E crítico e mutação seletiva exigida. "
        "Normalizar a prova com `mutation-evidence verify`, ligada ao HEAD/RC e ao `risk_seam`. No release, executar "
        "os comandos completos aprovados. Não perseguir cobertura ou mutation score global.\n",
    )
    gates = ROOT / "skills/_shared/ADAPTIVE_GATES.md"
    replace_once(
        gates,
        "Não bloquear por percentual ou score global. Bloquear somente mutante sobrevivente que demonstre alteração de comportamento aprovado de risco alto/crítico sem falha do teste. Justificar equivalentes e inalcançáveis sem criar campanha de cobertura.\n",
        "Não bloquear por percentual ou score global. Registrar com `mutation-evidence verify` e bloquear somente "
        "mutante sobrevivente que demonstre alteração de comportamento aprovado de risco alto/crítico sem falha do teste. "
        "Justificar equivalentes e inalcançáveis sem criar campanha de cobertura.\n",
    )


def main() -> int:
    patch_cli()
    patch_entrypoint()
    patch_readme()
    patch_changelog()
    patch_contract()
    patch_skills()
    print("Integração v3.1 aplicada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
