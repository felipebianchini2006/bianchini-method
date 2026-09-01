package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func runCycleClose(args []string) (any, error) {
	flags, err := parseFlags(args, map[string]bool{"--repo": true, "--change": true}, map[string]bool{})
	if err != nil {
		return nil, err
	}
	change := lastValue(flags, "--change")
	if change == "" {
		return nil, argparseError("the following arguments are required: --change")
	}
	repo := lastValue(flags, "--repo")
	if repo == "" {
		repo, err = os.Getwd()
		if err != nil {
			return nil, err
		}
	}
	root, err := repositoryRoot(repo)
	if err != nil {
		return nil, err
	}
	return closeChange(root, change)
}

func closeChange(root, change string) (map[string]any, error) {
	preparingRecovered := false
	pending, err := readCloseJournal(root)
	if err != nil {
		return nil, err
	}
	if pending != nil {
		if pending.Change != change {
			return nil, closeError("CLOSE_CONFLICT", "fechamento pendente pertence a "+pending.Change)
		}
		recovered, err := recoverPendingClose(root)
		if err != nil {
			return nil, err
		}
		if recovered == nil {
			return nil, closeError("JOURNAL_CORRUPT", "journal desapareceu durante recovery")
		}
		if recovered["status"] != "restored" {
			model, loadErr := loadProjectModel(filepath.Join(root, ".bianchini", "current", "SYSTEM_MODEL.md"))
			if loadErr != nil {
				return nil, workflowError("MODEL_MISMATCH", loadErr.Error())
			}
			recovered["model_digest"], recovered["specs_promoted"], recovered["specs_status"] = model.digest(), true, "managed"
			return recovered, nil
		}
		preparingRecovered = true
	}
	status, err := executionWorkspaceGitCommand(root, "status", "--porcelain")
	if err != nil {
		return nil, executionWorkspaceGitError(err)
	}
	if status != "" {
		return nil, workflowError("DIRTY_WORKSPACE", "fechamento exige Git limpo")
	}
	pack, err := loadCoherencePackage(root, change)
	if err != nil {
		return nil, err
	}
	coherence := pack.contract
	if stateString(coherence["status"]) != "approved" {
		return nil, workflowError("COHERENCE_ERROR", "fechamento exige COHERENCE approved")
	}
	if len(stateStringSlice(coherence["stale_plans"])) > 0 {
		return nil, workflowError("IMPACT_STALE", "fechamento contém planos stale")
	}
	findings, findingsOK := coherence["findings"].([]any)
	semantic, semanticOK := coherence["semantic"].(map[string]any)
	if !findingsOK || !semanticOK {
		return nil, workflowError("COHERENCE_ERROR", "auditoria global está incompleta")
	}
	if err := coherenceAssertCurrent(pack, coherence); err != nil {
		return nil, err
	}
	manifest := map[string]string{}
	specPackage := map[string]any{}
	if pack.planningContract >= 2 {
		manifest, err = coherenceArtifactManifest(pack.workspace, pack.directory)
		if err != nil {
			return nil, err
		}
	}
	if pack.specContract == 1 {
		specPackage, err = loadModelSpecPackage(pack.workspace, pack.directory, coherence)
		if err != nil {
			return nil, err
		}
	}
	packageDigest := coherencePackageDigest(pack.current, pack.expected, pack.plans, findings, semantic, pack.planningContract, manifest, specPackage)
	if pack.planningContract < 2 && packageDigest != stateString(coherence["digest"]) {
		return nil, workflowError("STALE_EVIDENCE", "pacote aprovado mudou após o checkpoint")
	}
	results, err := planResultPayloads(pack.workspace, pack.directory)
	if err != nil {
		return nil, err
	}
	missing := []string{}
	for _, plan := range pack.plans {
		if results[plan.id] == nil {
			missing = append(missing, plan.id)
		}
	}
	if len(missing) > 0 {
		return nil, workflowError("DOCVIVA_INCOMPLETE", "resultados ausentes: "+strings.Join(missing, ", "))
	}
	for _, plan := range pack.plans {
		result := results[plan.id]
		delta, ok := result["actual_delta"].(map[string]any)
		if !ok || !mapsEqual(delta, plan.modelDelta) {
			return nil, workflowError("IMPACT_STALE", "resultado de "+plan.id+" diverge do delta aprovado")
		}
		if !waveEvidence(result["verification"]) {
			return nil, workflowError("STALE_EVIDENCE", "resultado de "+plan.id+" não possui verificação")
		}
		if plan.schema == 2 {
			completed, ok := waveExactStringList(result["completed_tasks"])
			if !ok || !sameStrings(completed, planTaskIDs(plan)) {
				return nil, workflowError("DOCVIVA_INCOMPLETE", "resultado de "+plan.id+" não comprova todas as tarefas")
			}
		}
	}
	calculated, err := effectiveProjectModel(pack.current, pack.plans, results)
	if err != nil {
		return nil, err
	}
	if len(calculated.differences(pack.expected)) > 0 {
		return nil, workflowError("MODEL_MISMATCH", "modelo entregue diverge do SYSTEM_MODEL final")
	}
	requirements := []string{}
	if pack.planningContract >= 2 {
		requirements, err = coherenceRequirements(pack.workspace, pack.directory)
		if err != nil {
			return nil, err
		}
	}
	for _, raw := range coherenceStructuralFindings(pack.current, pack.expected, pack.plans, requirements, pack.planningContract >= 2) {
		if stateString(stateObject(raw)["severity"]) == "ERROR" {
			return nil, workflowError("COHERENCE_ERROR", "auditoria estrutural final encontrou ERROR")
		}
	}
	archive := filepath.Join(pack.workspace.dir, "archive", filepath.Base(pack.directory))
	if err := pack.workspace.validateWorkspacePath(archive); err != nil {
		return nil, err
	}
	if _, err := os.Lstat(archive); err == nil {
		return nil, workflowError("COHERENCE_ERROR", "arquivo já existe: "+filepath.Base(archive))
	}
	summary := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "status": "completed",
		"plans": planIdentifiers(pack.plans), "coherence_digest": packageDigest,
		"final_model_digest": pack.expected.digest(), "closed_at": utcNow(),
	}
	if pack.specContract == 1 {
		summary["specs_promoted"], summary["specs_status"] = true, "managed"
		for key, value := range specPackage {
			summary[key] = value
		}
	}
	summaryDocument, _ := frontmatterDocument(summary, "# Resumo\n\nMudança "+filepath.Base(pack.directory)+" concluída com "+fmt.Sprintf("%d", len(pack.plans))+" plano(s) verificado(s).", false)
	if pack.specContract == 1 {
		state, err := pack.workspace.readState()
		if err != nil {
			return nil, err
		}
		state["active_work"], state["current_unit"], state["status"], state["blockers"] = nil, nil, "idle", []any{}
		state["next_action"] = "Iniciar o próximo trabalho a partir do modelo atual."
		state["last_completed"] = map[string]any{"kind": "change", "id": filepath.Base(pack.directory), "status": "completed"}
		state["pointers"] = map[string]any{
			"architecture": ".bianchini/current/ARCHITECTURE.md", "system_model": ".bianchini/current/SYSTEM_MODEL.md",
			"specs": ".bianchini/current/specs", "coherence": ".bianchini/archive/" + filepath.Base(pack.directory) + "/COHERENCE.md",
		}
		state["digest"], state["updated_at"] = pack.expected.digest(), utcNow()
		normalized, err := pack.workspace.validateState(state)
		if err != nil {
			return nil, err
		}
		stateJSON, _ := canonicalJSON(normalized)
		nextState := append([]byte("---\n"), stateJSON...)
		nextState = append(nextState, []byte("\n---\n# Estado atual\n")...)
		result, err := crashRecoverableClose(
			root, filepath.Base(pack.directory), filepath.Join(pack.directory, "specs", "expected"),
			filepath.Join(pack.directory, "specs", "MANIFEST.json"), summaryDocument, nextState, "",
		)
		if err != nil {
			return nil, err
		}
		if preparingRecovered {
			result["recovered"] = true
		}
		result["model_digest"], result["specs_promoted"], result["specs_status"] = pack.expected.digest(), true, "managed"
		return result, nil
	}
	return closeLegacyChange(pack, archive, summaryDocument)
}

func closeLegacyChange(pack coherencePackage, archive string, summary []byte) (map[string]any, error) {
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "SUMMARY.md"), summary); err != nil {
		return nil, err
	}
	architecturePath := filepath.Join(pack.directory, "ARCHITECTURE.md")
	modelPath := filepath.Join(pack.directory, "SYSTEM_MODEL.md")
	architecture, model := mustReadClose(architecturePath), mustReadClose(modelPath)
	previousArchitecture := mustReadClose(filepath.Join(pack.workspace.current, "ARCHITECTURE.md"))
	previousModel := mustReadClose(pack.workspace.currentMod)
	if architecture == nil || model == nil || previousArchitecture == nil || previousModel == nil {
		return nil, workflowError("MODEL_MISMATCH", "artefato final ausente")
	}
	moved := false
	if err := pack.workspace.atomicWrite(filepath.Join(pack.workspace.current, "ARCHITECTURE.md"), architecture); err != nil {
		return nil, err
	}
	if err := pack.workspace.atomicWrite(pack.workspace.currentMod, model); err != nil {
		_ = pack.workspace.atomicWrite(filepath.Join(pack.workspace.current, "ARCHITECTURE.md"), previousArchitecture)
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(archive), 0o755); err != nil {
		return nil, err
	}
	if err := os.Rename(pack.directory, archive); err != nil {
		_ = pack.workspace.atomicWrite(filepath.Join(pack.workspace.current, "ARCHITECTURE.md"), previousArchitecture)
		_ = pack.workspace.atomicWrite(pack.workspace.currentMod, previousModel)
		return nil, err
	}
	moved = true
	state, err := pack.workspace.readState()
	if err == nil {
		state["active_work"], state["current_unit"], state["status"], state["blockers"] = nil, nil, "idle", []any{}
		state["next_action"] = "Iniciar o próximo trabalho a partir do modelo atual."
		state["last_completed"] = map[string]any{"kind": "change", "id": filepath.Base(archive), "status": "completed"}
		state["pointers"] = map[string]any{
			"architecture": ".bianchini/current/ARCHITECTURE.md", "system_model": ".bianchini/current/SYSTEM_MODEL.md",
			"specs": ".bianchini/current/specs", "coherence": ".bianchini/archive/" + filepath.Base(archive) + "/COHERENCE.md",
		}
		state["digest"], state["updated_at"] = pack.expected.digest(), utcNow()
		err = pack.workspace.writeState(state, "# Estado atual")
	}
	if err != nil {
		if moved {
			_ = os.Rename(archive, pack.directory)
		}
		_ = pack.workspace.atomicWrite(filepath.Join(pack.workspace.current, "ARCHITECTURE.md"), previousArchitecture)
		_ = pack.workspace.atomicWrite(pack.workspace.currentMod, previousModel)
		return nil, err
	}
	return map[string]any{"change": filepath.Base(archive), "status": "completed", "archive": archive, "model_digest": pack.expected.digest()}, nil
}

func planIdentifiers(plans []planContract) []string {
	result := make([]string, len(plans))
	for index, plan := range plans {
		result[index] = plan.id
	}
	return result
}
