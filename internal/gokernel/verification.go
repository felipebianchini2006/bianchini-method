package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var verificationProofID = regexp.MustCompile(`^proof-[0-9a-f]{32}$`)
var verificationReviewID = regexp.MustCompile(`^review-[0-9a-f]{32}$`)

type verificationSpec struct {
	kind        string
	argv        []string
	cwd         string
	timeout     int
	proves      string
	description string
	cache       string
}

func runVerify(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "task", "plan", "release", "review", "status") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], map[string]bool{
		"--repo": true, "--change": true, "--plan": true, "--task": true,
		"--context-pack": true, "--evidence": true, "--retry-reason": true,
		"--scope": true, "--reviewer": true, "--verdict": true, "--proof": true,
		"--resolves-review": true, "--artifact-kind": true, "--finding": true, "--build": true, "--checksum": true, "--delivery": true,
	}, map[string]bool{})
	if err != nil {
		return nil, err
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
	if action == "status" {
		return verificationStatus(root, lastValue(flags, "--change"))
	}
	change := lastValue(flags, "--change")
	if change == "" {
		return nil, argparseError("the following arguments are required: --change")
	}
	pack, coherence, err := approvedPlanPackage(root, change)
	if err != nil {
		return nil, err
	}
	switch action {
	case "task":
		return verifyTask(pack, coherence, flags)
	case "plan":
		return verifyPlan(pack, coherence, flags)
	case "release":
		return verifyRelease(pack, coherence, flags)
	default:
		return recordVerificationReview(pack, flags)
	}
}

func verifyTask(pack coherencePackage, coherence map[string]any, flags parsedFlags) (map[string]any, error) {
	planID, taskID := lastValue(flags, "--plan"), lastValue(flags, "--task")
	packPath := lastValue(flags, "--context-pack")
	if planID == "" || taskID == "" || packPath == "" {
		return nil, userError("verify task exige --plan, --task e --context-pack")
	}
	plan, err := planByID(pack.plans, planID)
	if err != nil {
		return nil, err
	}
	if plan.schema != 2 {
		return nil, workflowError("MODEL_MISMATCH", "verify task exige plano schema 2")
	}
	if containsString(stateStringSlice(coherence["stale_plans"]), planID) {
		return nil, workflowError("IMPACT_STALE", planID+" está stale")
	}
	task := taskByID(plan, taskID)
	if task == nil {
		return nil, workflowError("MODEL_MISMATCH", "tarefa desconhecida: "+planID+"/"+taskID)
	}
	verified, err := verifyContextPack(pack.workspace.root, packPath)
	if err != nil {
		return nil, err
	}
	identity := strings.SplitN(filepath.Base(pack.directory), "-", 2)[0] + "/" + planID + "/" + taskID
	if stateString(verified["unit"]) != identity {
		return nil, workflowError("STALE_EVIDENCE", "context pack não pertence a "+identity)
	}
	spec, err := taskVerificationSpec(task)
	if err != nil {
		return nil, err
	}
	request := verificationRequest{
		pack: pack, scope: "task", plan: planID, task: taskID, unit: identity,
		seam:          stateString(task["risk_seam"]),
		packageDigest: stateString(coherence["digest"]), packDigest: stateString(verified["digest"]),
		retryReason: lastValue(flags, "--retry-reason"), evidence: lastValue(flags, "--evidence"),
	}
	return executeVerification(request, spec)
}

func verifyPlan(pack coherencePackage, coherence map[string]any, flags parsedFlags) (map[string]any, error) {
	planID := lastValue(flags, "--plan")
	if planID == "" {
		return nil, userError("verify plan exige --plan")
	}
	plan, err := planByID(pack.plans, planID)
	if err != nil {
		return nil, err
	}
	if containsString(stateStringSlice(coherence["stale_plans"]), planID) {
		return nil, workflowError("IMPACT_STALE", planID+" está stale")
	}
	proofs := []string{}
	for index, raw := range normalizedPlanStrings(plan, "verifications") {
		spec, specErr := commandVerificationSpec(raw, "gate do plano")
		if specErr != nil {
			return nil, specErr
		}
		proof, proofErr := executeVerification(verificationRequest{
			pack: pack, scope: "plan", plan: planID, unit: fmt.Sprintf("%s/gate-%02d", planID, index+1),
			seam:          "plan:" + plan.id,
			packageDigest: stateString(coherence["digest"]), retryReason: lastValue(flags, "--retry-reason"),
		}, spec)
		if proofErr != nil {
			return nil, proofErr
		}
		proofs = append(proofs, stateString(proof["proof_id"]))
	}
	return map[string]any{"change": filepath.Base(pack.directory), "plan": planID, "scope": "plan", "status": "passed", "proof_ids": proofs}, nil
}

func verifyRelease(pack coherencePackage, coherence map[string]any, flags parsedFlags) (map[string]any, error) {
	if stale := stateStringSlice(coherence["stale_plans"]); len(stale) > 0 {
		return nil, workflowError("IMPACT_STALE", "verify release contém planos stale: "+strings.Join(stale, ", "))
	}
	if err := verificationProductClean(pack.workspace.root); err != nil {
		return nil, err
	}
	requiredScenarios, err := requiredAcceptanceScenarios(pack)
	if err != nil {
		return nil, err
	}
	build, checksum := strings.TrimSpace(lastValue(flags, "--build")), strings.TrimSpace(lastValue(flags, "--checksum"))
	delivery := strings.TrimSpace(lastValue(flags, "--delivery"))
	if build == "" || (checksum != "" && !waveDigest.MatchString(checksum)) || !oneOf(delivery, "ready", "not_applicable") {
		return nil, userError("verify release exige --build e --delivery ready|not_applicable; --checksum opcional deve ser SHA-256")
	}
	kind := lastValue(flags, "--artifact-kind")
	if kind == "" {
		kind = "file"
	}
	build = canonicalArtifactBuild(pack.workspace.root, kind, build)
	checksum, err = releaseArtifactIdentity(pack.workspace.root, kind, build, checksum)
	if err != nil {
		return nil, err
	}
	head, err := verificationGitHead(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	candidate := map[string]any{"revision": head, "kind": kind, "build": build, "checksum": checksum, "package_digest": coherence["digest"]}
	fingerprint := waveStableDigest(candidate)
	candidate["id"] = "RC-" + fingerprint[:12]
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
		return nil, workflowError("DOCVIVA_INCOMPLETE", "verify release exige planos concluídos: "+strings.Join(missing, ", "))
	}
	proofs, manual := []string{}, []any{}
	for _, plan := range pack.plans {
		for _, task := range planTasks(plan) {
			spec, specErr := taskVerificationSpec(task)
			if specErr != nil {
				return nil, specErr
			}
			if spec.kind == "procedure" {
				manual = append(manual, map[string]any{"plan": plan.id, "task": stateString(task["id"]), "procedure": spec.description, "proves": spec.proves})
				continue
			}
		}
		for index, raw := range normalizedPlanStrings(plan, "verifications") {
			spec, specErr := commandVerificationSpec(raw, "gate de release")
			if specErr != nil {
				return nil, specErr
			}
			proof, proofErr := executeVerification(verificationRequest{
				pack: pack, scope: "release", plan: plan.id, unit: fmt.Sprintf("%s/gate-%02d", plan.id, index+1),
				seam: "plan:" + plan.id, candidateDigest: fingerprint, candidate: candidate,
				packageDigest: stateString(coherence["digest"]), retryReason: lastValue(flags, "--retry-reason"),
			}, spec)
			if proofErr != nil {
				return nil, proofErr
			}
			proofs = append(proofs, stateString(proof["proof_id"]))
		}
	}
	if err := verificationProductClean(pack.workspace.root); err != nil {
		return nil, err
	}
	sourceFingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	if err := validateCandidateArtifact(pack, candidate); err != nil {
		return nil, err
	}
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "status": "verified",
		"candidate": candidate, "fingerprint": fingerprint, "source_fingerprint": sourceFingerprint,
		"package_digest": coherence["digest"], "proof_ids": stringSliceAny(proofs),
		"manual_requirements": manual, "scenario_requirements": scenarioValues(requiredScenarios), "delivery": delivery, "review_id": nil, "verified_at": utcNow(),
	}
	document, _ := frontmatterDocument(payload, "# Release candidate\n\nBaseline automatizada executada pelo núcleo.", false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "results", "RELEASE.md"), document); err != nil {
		return nil, err
	}
	if err := createHomologationDraft(pack, candidate, fingerprint, requiredScenarios, proofs); err != nil {
		return nil, err
	}
	return map[string]any{"change": filepath.Base(pack.directory), "status": "verified", "candidate": candidate, "fingerprint": fingerprint, "proof_ids": proofs, "manual_requirements": manual, "scenario_requirements": scenarioValues(requiredScenarios), "homologation": homologationDocumentPath(pack, candidate), "delivery": delivery}, nil
}

func verificationStatus(root, change string) (map[string]any, error) {
	if change == "" {
		return nil, userError("verify status exige --change")
	}
	pack, _, err := approvedPlanPackage(root, change)
	if err != nil {
		return nil, err
	}
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	passed, failed := 0, 0
	for _, proof := range proofs {
		if stateString(proof["status"]) == "passed" {
			passed++
		} else {
			failed++
		}
	}
	return map[string]any{"change": filepath.Base(pack.directory), "proofs": len(proofs), "passed": passed, "failed": failed}, nil
}
