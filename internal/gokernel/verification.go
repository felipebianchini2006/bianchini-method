package gokernel

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strings"
	"time"
)

var verificationProofID = regexp.MustCompile(`^proof-[0-9a-f]{32}$`)
var verificationReviewID = regexp.MustCompile(`^review-[0-9a-f]{32}$`)

type verificationSpec struct {
	kind       string
	argv       []string
	cwd        string
	timeout    int
	proves     string
	legacyRun  string
	legacyMode bool
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
		"--finding": true, "--build": true, "--checksum": true, "--delivery": true,
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
		spec, specErr := legacyVerificationSpec(raw, "gate do plano")
		if specErr != nil {
			return nil, specErr
		}
		proof, proofErr := executeVerification(verificationRequest{
			pack: pack, scope: "plan", plan: planID, unit: fmt.Sprintf("%s/gate-%02d", planID, index+1),
			seam:          "plan-gate",
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
	build, checksum := strings.TrimSpace(lastValue(flags, "--build")), strings.TrimSpace(lastValue(flags, "--checksum"))
	delivery := strings.TrimSpace(lastValue(flags, "--delivery"))
	if build == "" || !waveDigest.MatchString(checksum) || !oneOf(delivery, "ready", "not_applicable") {
		return nil, userError("verify release exige --build, --checksum e --delivery ready|not_applicable")
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
				manual = append(manual, map[string]any{"plan": plan.id, "task": stateString(task["id"]), "procedure": spec.legacyRun, "proves": spec.proves})
				continue
			}
			proof, proofErr := executeVerification(verificationRequest{
				pack: pack, scope: "release", plan: plan.id, task: stateString(task["id"]),
				unit: plan.id + "/" + stateString(task["id"]), packageDigest: stateString(coherence["digest"]),
				seam:        stateString(task["risk_seam"]),
				retryReason: lastValue(flags, "--retry-reason"),
			}, spec)
			if proofErr != nil {
				return nil, proofErr
			}
			proofs = append(proofs, stateString(proof["proof_id"]))
		}
		for index, raw := range normalizedPlanStrings(plan, "verifications") {
			spec, specErr := legacyVerificationSpec(raw, "gate de release")
			if specErr != nil {
				return nil, specErr
			}
			proof, proofErr := executeVerification(verificationRequest{
				pack: pack, scope: "release", plan: plan.id, unit: fmt.Sprintf("%s/gate-%02d", plan.id, index+1),
				seam:          "plan-gate",
				packageDigest: stateString(coherence["digest"]), retryReason: lastValue(flags, "--retry-reason"),
			}, spec)
			if proofErr != nil {
				return nil, proofErr
			}
			proofs = append(proofs, stateString(proof["proof_id"]))
		}
	}
	head, err := verificationGitHead(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	sourceFingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	candidate := map[string]any{"revision": head, "build": build, "checksum": checksum}
	fingerprint := waveStableDigest(candidate)
	candidate["id"] = "RC-" + fingerprint[:12]
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "status": "verified",
		"candidate": candidate, "fingerprint": fingerprint, "source_fingerprint": sourceFingerprint,
		"package_digest": coherence["digest"], "proof_ids": stringSliceAny(proofs),
		"manual_requirements": manual, "delivery": delivery, "review_id": nil, "verified_at": utcNow(),
	}
	document, _ := frontmatterDocument(payload, "# Release candidate\n\nBaseline automatizada executada pelo núcleo.", false)
	if err := pack.workspace.atomicWrite(filepath.Join(pack.directory, "results", "RELEASE.md"), document); err != nil {
		return nil, err
	}
	return map[string]any{"change": filepath.Base(pack.directory), "status": "verified", "candidate": candidate, "fingerprint": fingerprint, "proof_ids": proofs, "manual_requirements": manual, "delivery": delivery}, nil
}

func taskByID(plan planContract, identifier string) map[string]any {
	var selected map[string]any
	for _, task := range planTasks(plan) {
		if stateString(task["id"]) == identifier {
			if selected != nil {
				return nil
			}
			selected = task
		}
	}
	return selected
}

func taskVerificationSpec(task map[string]any) (verificationSpec, error) {
	verify := stateObject(task["verify"])
	kind := stateString(verify["kind"])
	spec := verificationSpec{
		kind: kind, cwd: strings.TrimSpace(stateString(verify["cwd"])),
		timeout: stateInt(verify["timeout_seconds"]), proves: strings.TrimSpace(stateString(verify["proves"])),
		legacyRun: strings.TrimSpace(stateString(verify["run"])),
	}
	if spec.cwd == "" {
		spec.cwd = "."
	}
	if spec.timeout == 0 {
		spec.timeout = 300
	}
	if kind == "procedure" {
		return spec, nil
	}
	argv, err := stringValues(verify["argv"], "verify.argv")
	if err != nil {
		return verificationSpec{}, workflowError("MODEL_MISMATCH", err.Error())
	}
	if len(argv) > 0 {
		spec.argv = argv
		return spec, nil
	}
	return legacyVerificationSpecWith(spec, spec.legacyRun)
}

func legacyVerificationSpec(raw, proves string) (verificationSpec, error) {
	return legacyVerificationSpecWith(verificationSpec{kind: "command", cwd: ".", timeout: 300, proves: proves, legacyRun: strings.TrimSpace(raw)}, raw)
}

func legacyVerificationSpecWith(spec verificationSpec, raw string) (verificationSpec, error) {
	argv, err := splitVerificationCommand(raw)
	if err != nil {
		return verificationSpec{}, workflowError("MODEL_MISMATCH", "verificação legada inválida: "+err.Error()+"; declare verify.argv")
	}
	spec.argv, spec.legacyMode = argv, true
	return spec, nil
}

func splitVerificationCommand(raw string) ([]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("comando vazio")
	}
	result, current := []string{}, strings.Builder{}
	quote := rune(0)
	escaped := false
	flush := func() {
		if current.Len() > 0 {
			result = append(result, current.String())
			current.Reset()
		}
	}
	for _, character := range raw {
		if escaped {
			current.WriteRune(character)
			escaped = false
			continue
		}
		if character == '\\' && quote != '\'' {
			escaped = true
			continue
		}
		if quote != 0 {
			if character == quote {
				quote = 0
			} else {
				current.WriteRune(character)
			}
			continue
		}
		if character == '\'' || character == '"' {
			quote = character
			continue
		}
		if strings.ContainsRune("|&;<>`", character) {
			return nil, fmt.Errorf("operador de shell %q não é permitido", character)
		}
		if character == ' ' || character == '\t' || character == '\n' {
			flush()
			continue
		}
		current.WriteRune(character)
	}
	if escaped || quote != 0 {
		return nil, fmt.Errorf("aspas ou escape incompletos")
	}
	flush()
	if len(result) == 0 {
		return nil, fmt.Errorf("comando vazio")
	}
	return result, nil
}

type verificationRequest struct {
	pack          coherencePackage
	scope         string
	plan          string
	task          string
	unit          string
	seam          string
	packageDigest string
	packDigest    string
	retryReason   string
	evidence      string
}

func executeVerification(request verificationRequest, spec verificationSpec) (map[string]any, error) {
	if strings.TrimSpace(request.seam) == "" {
		return nil, workflowError("MODEL_MISMATCH", "verificação exige risk_seam explícito")
	}
	fingerprint, err := verificationSourceFingerprint(request.pack.workspace.root)
	if err != nil {
		return nil, err
	}
	head, err := verificationGitHead(request.pack.workspace.root)
	if err != nil {
		return nil, err
	}
	evidencePath, evidenceDigest := any(nil), any(nil)
	if spec.kind == "procedure" {
		if request.evidence == "" {
			return nil, workflowError("MANUAL_PROOF_REQUIRED", "procedimento exige --evidence apontando para artefato real")
		}
		path, pathErr := confinedPath(request.pack.workspace.root, request.evidence, "evidence", true)
		if pathErr != nil {
			return nil, pathErr
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil || len(content) == 0 {
			return nil, workflowError("MANUAL_PROOF_REQUIRED", "evidence deve ser arquivo não vazio")
		}
		relative, _ := filepath.Rel(request.pack.workspace.root, path)
		evidencePath, evidenceDigest = filepath.ToSlash(relative), sha256Bytes(content)
	}
	base := map[string]any{
		"scope": request.scope, "change": filepath.Base(request.pack.directory), "plan": request.plan,
		"task": nullableString(request.task), "unit": request.unit, "kind": spec.kind,
		"risk_seam": request.seam,
		"argv":      stringSliceAny(spec.argv), "cwd": spec.cwd, "timeout_seconds": spec.timeout,
		"proves": spec.proves, "legacy_command": spec.legacyMode, "source_revision": head,
		"source_fingerprint": fingerprint, "package_digest": request.packageDigest,
		"context_pack_digest":     nullableString(request.packDigest),
		"environment_fingerprint": verificationEnvironmentFingerprint(spec.argv),
		"evidence_path":           evidencePath,
		"evidence_sha256":         evidenceDigest,
	}
	executionKey := waveStableDigest(base)
	existing, err := matchingVerificationProofs(request.pack, executionKey)
	if err != nil {
		return nil, err
	}
	for _, proof := range existing {
		if stateString(proof["status"]) == "passed" {
			return map[string]any{"proof_id": proof["proof_id"], "status": "passed", "reused": true, "proof": proof}, nil
		}
	}
	if len(existing) > 0 && strings.TrimSpace(request.retryReason) == "" {
		return nil, workflowError("VERIFICATION_RETRY_REQUIRED", "a mesma verificação já falhou neste estado; informe --retry-reason para repetir")
	}
	attempt := len(existing) + 1
	started := utcNow()
	exitCode, timedOut, spawnError := 0, false, false
	stdout, stderr := []byte{}, []byte{}
	if spec.kind != "procedure" {
		cwd, cwdErr := verificationCWD(request.pack.workspace.root, spec.cwd)
		if cwdErr != nil {
			return nil, cwdErr
		}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(spec.timeout)*time.Second)
		command := exec.CommandContext(ctx, spec.argv[0], spec.argv[1:]...)
		command.Dir = cwd
		var stdoutBuffer, stderrBuffer bytes.Buffer
		command.Stdout, command.Stderr = &stdoutBuffer, &stderrBuffer
		runErr := command.Run()
		cancel()
		stdout, stderr = stdoutBuffer.Bytes(), stderrBuffer.Bytes()
		if ctx.Err() == context.DeadlineExceeded {
			timedOut = true
		}
		if runErr != nil {
			if exit, ok := runErr.(*exec.ExitError); ok {
				exitCode = exit.ExitCode()
			} else {
				exitCode, spawnError = 127, true
				stderr = append(stderr, []byte(runErr.Error())...)
			}
		}
	}
	status := "passed"
	if exitCode != 0 || timedOut || spawnError {
		status = "failed"
	}
	record := cloneMap(base)
	record["schema_version"] = 1
	record["execution_key"] = executionKey
	record["attempt"] = attempt
	record["retry_reason"] = nullableString(strings.TrimSpace(request.retryReason))
	record["exit_code"] = exitCode
	record["timed_out"] = timedOut
	record["spawn_error"] = spawnError
	record["stdout_sha256"] = sha256Bytes(stdout)
	record["stderr_sha256"] = sha256Bytes(stderr)
	record["evidence_path"] = evidencePath
	record["evidence_sha256"] = evidenceDigest
	record["status"] = status
	record["started_at"] = started
	record["finished_at"] = utcNow()
	idMaterial := cloneMap(record)
	delete(idMaterial, "started_at")
	delete(idMaterial, "finished_at")
	proofID := "proof-" + waveStableDigest(idMaterial)[:32]
	record["proof_id"] = proofID
	record["record_digest"] = verificationRecordDigest(record)
	path := filepath.Join(request.pack.directory, "results", "proofs", proofID+".json")
	encoded, _ := json.MarshalIndent(record, "", "  ")
	if err := request.pack.workspace.atomicWrite(path, append(encoded, '\n')); err != nil {
		return nil, err
	}
	if status != "passed" {
		return nil, workflowError("VERIFICATION_FAILED", fmt.Sprintf("%s falhou com exit code %d; proof_id %s", request.unit, exitCode, proofID))
	}
	return map[string]any{"proof_id": proofID, "status": status, "reused": false, "proof": record}, nil
}

func verificationCWD(root, relative string) (string, error) {
	if relative == "." {
		return root, nil
	}
	if err := validateRelativePath(filepath.ToSlash(relative), "verify.cwd"); err != nil {
		return "", err
	}
	path := filepath.Join(root, filepath.FromSlash(relative))
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", workflowError("PATH_SAFETY", "verify.cwd deve ser diretório real dentro do repo")
	}
	return path, nil
}

func verificationGitHead(root string) (string, error) {
	head, err := workflowGit(root, "rev-parse", "--verify", "HEAD")
	if err != nil || !regexp.MustCompile(`^[0-9a-f]{40,64}$`).MatchString(head) {
		return "", workflowError("STALE_EVIDENCE", "verificação exige HEAD Git commitado")
	}
	return head, nil
}

func verificationEnvironmentFingerprint(argv []string) string {
	executable, executableDigest := "", ""
	if len(argv) > 0 {
		executable, _ = exec.LookPath(argv[0])
		if resolved, err := filepath.EvalSymlinks(executable); err == nil {
			executable = resolved
		}
		if content, err := os.ReadFile(executable); err == nil {
			executableDigest = sha256Bytes(content)
		}
	}
	environment := os.Environ()
	sort.Strings(environment)
	return waveStableDigest(map[string]any{
		"goos": runtime.GOOS, "goarch": runtime.GOARCH,
		"executable": executable, "executable_sha256": executableDigest,
		"environment_sha256": sha256Bytes([]byte(strings.Join(environment, "\x00"))),
	})
}

func verificationRecordDigest(record map[string]any) string {
	copy := cloneMap(record)
	delete(copy, "record_digest")
	return waveStableDigest(copy)
}

func matchingVerificationProofs(pack coherencePackage, executionKey string) ([]map[string]any, error) {
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	result := []map[string]any{}
	for _, proof := range proofs {
		if stateString(proof["execution_key"]) == executionKey {
			result = append(result, proof)
		}
	}
	sort.Slice(result, func(i, j int) bool { return stateInt(result[i]["attempt"]) < stateInt(result[j]["attempt"]) })
	return result, nil
}

func loadVerificationProofs(pack coherencePackage) (map[string]map[string]any, error) {
	directory := filepath.Join(pack.directory, "results", "proofs")
	entries, err := os.ReadDir(directory)
	if os.IsNotExist(err) {
		return map[string]map[string]any{}, nil
	}
	if err != nil {
		return nil, workflowError("STALE_EVIDENCE", "proof store ilegível")
	}
	result := map[string]map[string]any{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			return nil, workflowError("STALE_EVIDENCE", "proof store contém entrada inválida")
		}
		content, readErr := os.ReadFile(filepath.Join(directory, entry.Name()))
		if readErr != nil {
			return nil, workflowError("STALE_EVIDENCE", "proof ilegível: "+entry.Name())
		}
		proof, decodeErr := decodeStrictJSONObject(content)
		if decodeErr != nil {
			return nil, workflowError("STALE_EVIDENCE", "proof inválido: "+entry.Name())
		}
		identifier := stateString(proof["proof_id"])
		if !verificationProofID.MatchString(identifier) || entry.Name() != identifier+".json" || stateString(proof["record_digest"]) != verificationRecordDigest(proof) {
			return nil, workflowError("STALE_EVIDENCE", "proof adulterado: "+entry.Name())
		}
		result[identifier] = proof
	}
	return result, nil
}

func validateProofSet(pack coherencePackage, identifiers []string, scope, plan, task string, requireCurrent bool) ([]string, error) {
	ids := nonemptyUnique(identifiers)
	if len(ids) == 0 {
		return nil, workflowError("STALE_EVIDENCE", "conclusão exige proof_id gerado por bm verify")
	}
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return nil, err
	}
	current := ""
	if requireCurrent {
		current, err = verificationSourceFingerprint(pack.workspace.root)
		if err != nil {
			return nil, err
		}
	}
	for _, identifier := range ids {
		proof := proofs[identifier]
		if proof == nil || stateString(proof["status"]) != "passed" || stateString(proof["scope"]) != scope || stateString(proof["change"]) != filepath.Base(pack.directory) || stateString(proof["package_digest"]) != stateString(pack.contract["digest"]) || scope != "release" && stateString(proof["plan"]) != plan {
			return nil, workflowError("STALE_EVIDENCE", "proof_id incompatível: "+identifier)
		}
		if task != "" && stateString(proof["task"]) != task {
			return nil, workflowError("STALE_EVIDENCE", "proof_id pertence a outra tarefa: "+identifier)
		}
		if requireCurrent && stateString(proof["source_fingerprint"]) != current {
			return nil, workflowError("STALE_EVIDENCE", "proof_id não pertence ao estado atual do código: "+identifier)
		}
		if requireCurrent && !verificationProofEnvironmentCurrent(pack.workspace.root, proof) {
			return nil, workflowError("STALE_EVIDENCE", "proof_id não pertence ao ambiente ou evidência atual: "+identifier)
		}
	}
	return ids, nil
}

func verificationProofEnvironmentCurrent(root string, proof map[string]any) bool {
	if stateString(proof["kind"]) == "procedure" {
		path, err := confinedPath(root, stateString(proof["evidence_path"]), "proof.evidence", true)
		if err != nil {
			return false
		}
		content, err := os.ReadFile(path)
		return err == nil && len(content) > 0 && sha256Bytes(content) == stateString(proof["evidence_sha256"])
	}
	argv, ok := waveExactStringList(proof["argv"])
	return ok && len(argv) > 0 && stateString(proof["environment_fingerprint"]) == verificationEnvironmentFingerprint(argv)
}

func validateProofContext(pack coherencePackage, identifiers []string, contextDigest string) error {
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	for _, identifier := range identifiers {
		if stateString(proofs[identifier]["context_pack_digest"]) != contextDigest {
			return workflowError("STALE_EVIDENCE", "proof_id não pertence ao context pack usado: "+identifier)
		}
	}
	return nil
}

func recordVerificationReview(pack coherencePackage, flags parsedFlags) (map[string]any, error) {
	scope, reviewer, verdict := lastValue(flags, "--scope"), strings.TrimSpace(lastValue(flags, "--reviewer")), lastValue(flags, "--verdict")
	planID, taskID := lastValue(flags, "--plan"), lastValue(flags, "--task")
	if !oneOf(scope, "task", "plan", "release") || reviewer == "" || !oneOf(verdict, "approved", "changes_requested") {
		return nil, userError("verify review exige --scope task|plan|release, --reviewer e --verdict approved|changes_requested")
	}
	if (scope != "release" && planID == "") || (scope == "task" && taskID == "") {
		return nil, userError("verify review exige identidade completa do escopo")
	}
	proofIDs := nonemptyUnique(flags.values["--proof"])
	if len(proofIDs) == 0 {
		return nil, workflowError("STALE_EVIDENCE", "review exige ao menos um --proof")
	}
	if err := validateReviewProofs(pack, proofIDs, scope, planID, taskID, verdict); err != nil {
		return nil, err
	}
	findings := nonemptyUnique(flags.values["--finding"])
	if verdict == "approved" && len(findings) > 0 {
		return nil, workflowError("REVIEW_BLOCKED", "review approved não aceita finding aberto")
	}
	if verdict == "changes_requested" && len(findings) == 0 {
		return nil, workflowError("REVIEW_BLOCKED", "changes_requested exige ao menos um --finding")
	}
	fingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	payload := map[string]any{
		"schema_version": 1, "change": filepath.Base(pack.directory), "scope": scope,
		"plan": nullableString(planID), "task": nullableString(taskID), "reviewer": reviewer,
		"verdict": verdict, "proof_ids": stringSliceAny(proofIDs), "findings": stringSliceAny(findings),
		"source_fingerprint": fingerprint, "reviewed_at": utcNow(),
	}
	idMaterial := cloneMap(payload)
	delete(idMaterial, "reviewed_at")
	reviewID := "review-" + waveStableDigest(idMaterial)[:32]
	payload["review_id"] = reviewID
	payload["record_digest"] = verificationRecordDigest(payload)
	path := filepath.Join(pack.directory, "results", "reviews", reviewID+".json")
	encoded, _ := json.MarshalIndent(payload, "", "  ")
	if err := pack.workspace.atomicWrite(path, append(encoded, '\n')); err != nil {
		return nil, err
	}
	if scope == "release" && verdict == "approved" {
		if err := attachReleaseReview(pack, reviewID, proofIDs); err != nil {
			return nil, err
		}
	}
	return map[string]any{"review_id": reviewID, "verdict": verdict, "scope": scope, "proof_ids": proofIDs}, nil
}

func validateReviewProofs(pack coherencePackage, identifiers []string, scope, plan, task, verdict string) error {
	if verdict == "approved" {
		_, err := validateProofSet(pack, identifiers, scope, plan, task, true)
		return err
	}
	proofs, err := loadVerificationProofs(pack)
	if err != nil {
		return err
	}
	current, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return err
	}
	hasFailure := false
	for _, identifier := range identifiers {
		proof := proofs[identifier]
		if proof == nil || stateString(proof["scope"]) != scope || stateString(proof["change"]) != filepath.Base(pack.directory) || stateString(proof["package_digest"]) != stateString(pack.contract["digest"]) || (scope != "release" && stateString(proof["plan"]) != plan) || (task != "" && stateString(proof["task"]) != task) || stateString(proof["source_fingerprint"]) != current || !verificationProofEnvironmentCurrent(pack.workspace.root, proof) {
			return workflowError("STALE_EVIDENCE", "proof_id incompatível: "+identifier)
		}
		if stateString(proof["status"]) == "failed" {
			hasFailure = true
		}
	}
	if !hasFailure {
		return workflowError("REVIEW_BLOCKED", "changes_requested exige ao menos um proof vermelho no estado atual")
	}
	return nil
}

func attachReleaseReview(pack coherencePackage, reviewID string, proofIDs []string) error {
	path := filepath.Join(pack.directory, "results", "RELEASE.md")
	release, err := readStructuredFrontmatter(path)
	if err != nil {
		return workflowError("REVIEW_REQUIRED", "verify release deve executar antes da revisão final")
	}
	releaseProofs, ok := waveExactStringList(release["proof_ids"])
	if !ok || !sameStrings(releaseProofs, proofIDs) {
		return workflowError("REVIEW_REQUIRED", "revisão final não cobre exatamente o release atual")
	}
	release["review_id"], release["status"], release["reviewed_at"] = reviewID, "reviewed", utcNow()
	document, _ := frontmatterDocument(release, "# Release candidate\n\nBaseline automatizada e revisão final aprovadas.", false)
	return pack.workspace.atomicWrite(path, document)
}

func validateVerificationReview(pack coherencePackage, identifier, scope, plan, task string, proofIDs []string, requireCurrent bool) error {
	if !verificationReviewID.MatchString(identifier) {
		return workflowError("REVIEW_REQUIRED", "conclusão exige review_id gerado por bm verify review")
	}
	path := filepath.Join(pack.directory, "results", "reviews", identifier+".json")
	content, err := os.ReadFile(path)
	if err != nil {
		return workflowError("REVIEW_REQUIRED", "review_id não encontrado: "+identifier)
	}
	review, err := decodeStrictJSONObject(content)
	if err != nil || stateString(review["review_id"]) != identifier || stateString(review["record_digest"]) != verificationRecordDigest(review) {
		return workflowError("REVIEW_REQUIRED", "review adulterado: "+identifier)
	}
	if stateString(review["verdict"]) != "approved" || stateString(review["scope"]) != scope || stateString(review["change"]) != filepath.Base(pack.directory) || stateString(review["plan"]) != plan || stateString(review["task"]) != task {
		return workflowError("REVIEW_REQUIRED", "review incompatível: "+identifier)
	}
	reviewProofs, ok := waveExactStringList(review["proof_ids"])
	if !ok || !sameStrings(reviewProofs, proofIDs) {
		return workflowError("REVIEW_REQUIRED", "review não cobre exatamente os proofs informados")
	}
	if requireCurrent {
		fingerprint, fingerprintErr := verificationSourceFingerprint(pack.workspace.root)
		if fingerprintErr != nil {
			return fingerprintErr
		}
		if stateString(review["source_fingerprint"]) != fingerprint {
			return workflowError("STALE_EVIDENCE", "review não pertence ao estado atual do código")
		}
	}
	return nil
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

func verificationSourceFingerprint(root string) (string, error) {
	command := exec.Command("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
	command.Dir = root
	output, err := command.Output()
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "não foi possível inventariar o código")
	}
	paths := []string{}
	for _, raw := range bytes.Split(output, []byte{0}) {
		relative := filepath.ToSlash(string(raw))
		if relative == "" || relative == ".bianchini" || strings.HasPrefix(relative, ".bianchini/") || relative == ".planning" || strings.HasPrefix(relative, ".planning/") {
			continue
		}
		if err := validateRiskPath(relative); err != nil {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código escapou do repo")
		}
		paths = append(paths, relative)
	}
	sort.Strings(paths)
	digest := sha256.New()
	for _, relative := range paths {
		path := filepath.Join(root, filepath.FromSlash(relative))
		info, statErr := os.Lstat(path)
		if os.IsNotExist(statErr) {
			_, _ = digest.Write([]byte(relative + "\x00deleted\x00"))
			continue
		}
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código não é regular: "+relative)
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código ilegível: "+relative)
		}
		_, _ = digest.Write([]byte(relative + "\x00" + info.Mode().Perm().String() + "\x00"))
		fileDigest := sha256.Sum256(content)
		_, _ = digest.Write(fileDigest[:])
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}

func validateReleaseClosure(pack coherencePackage, coherence map[string]any) (map[string]any, error) {
	releasePath := filepath.Join(pack.directory, "results", "RELEASE.md")
	release, err := readStructuredFrontmatter(releasePath)
	if err != nil {
		return nil, workflowError("RELEASE_REQUIRED", "fechamento exige bm verify release")
	}
	if stateInt(release["schema_version"]) != 1 || stateString(release["change"]) != filepath.Base(pack.directory) || stateString(release["status"]) != "reviewed" || !oneOf(stateString(release["delivery"]), "ready", "not_applicable") || stateString(release["package_digest"]) != stateString(coherence["digest"]) {
		return nil, workflowError("RELEASE_REQUIRED", "RELEASE.md está incompleto ou obsoleto")
	}
	currentFingerprint, err := verificationSourceFingerprint(pack.workspace.root)
	if err != nil {
		return nil, err
	}
	if stateString(release["source_fingerprint"]) != currentFingerprint {
		return nil, workflowError("STALE_EVIDENCE", "release não pertence ao estado atual do código")
	}
	proofIDs, ok := waveExactStringList(release["proof_ids"])
	if !ok {
		return nil, workflowError("RELEASE_REQUIRED", "RELEASE.md não declara proofs válidos")
	}
	if _, err := validateProofSet(pack, proofIDs, "release", "", "", true); err != nil {
		return nil, err
	}
	reviewID := stateString(release["review_id"])
	if err := validateVerificationReview(pack, reviewID, "release", "", "", proofIDs, true); err != nil {
		return nil, err
	}
	candidate, ok := release["candidate"].(map[string]any)
	if !ok || stateString(candidate["id"]) == "" || stateString(candidate["revision"]) == "" || stateString(candidate["build"]) == "" || stateString(candidate["checksum"]) == "" {
		return nil, workflowError("RELEASE_REQUIRED", "fingerprint do RC está incompleto")
	}
	fingerprintMaterial := cloneMap(candidate)
	delete(fingerprintMaterial, "id")
	fingerprint := waveStableDigest(fingerprintMaterial)
	if stateString(release["fingerprint"]) != fingerprint || stateString(candidate["id"]) != "RC-"+fingerprint[:12] {
		return nil, workflowError("RELEASE_REQUIRED", "fingerprint do RC diverge")
	}
	if err := verificationOnlyMethodChangesSince(pack.workspace.root, stateString(candidate["revision"])); err != nil {
		return nil, err
	}
	homologation, err := readStructuredFrontmatter(filepath.Join(pack.directory, "results", "HOMOLOGATION.md"))
	if err != nil {
		return nil, workflowError("HOMOLOGATION_REQUIRED", "fechamento exige HOMOLOGATION.md antes do archive")
	}
	blockers, blockersOK := homologation["blockers"].([]any)
	gates, gatesOK := homologation["gates"].([]any)
	rc := homologation["rc"]
	if rc == nil {
		rc = homologation["candidate"]
	}
	if stateInt(homologation["schema_version"]) != 1 || stateString(homologation["change"]) != filepath.Base(pack.directory) || stateString(homologation["status"]) != "accepted" || stateString(homologation["fingerprint"]) != fingerprint || !mapsEqual(stateObject(rc), candidate) || !blockersOK || len(blockers) > 0 || !gatesOK || len(gates) == 0 {
		return nil, workflowError("HOMOLOGATION_REQUIRED", "homologação aceita do RC exato está ausente ou incompleta")
	}
	manualRequirements := stateArray(release["manual_requirements"])
	if len(manualRequirements) > 0 {
		manualProofs := stateArray(homologation["manual_proofs"])
		if !manualProofCoverage(pack.workspace.root, manualRequirements, manualProofs) {
			return nil, workflowError("HOMOLOGATION_REQUIRED", "homologação não comprova todos os procedimentos manuais")
		}
	}
	return release, nil
}

func manualProofCoverage(root string, requirements, proofs []any) bool {
	covered := map[string]bool{}
	for _, raw := range proofs {
		proof := stateObject(raw)
		planID, taskID := stateString(proof["plan"]), stateString(proof["task"])
		evidence, expectedDigest := stateString(proof["evidence"]), stateString(proof["evidence_sha256"])
		if planID == "" || taskID == "" || evidence == "" || !waveDigest.MatchString(expectedDigest) {
			continue
		}
		path, err := confinedPath(root, evidence, "manual_proof.evidence", true)
		if err != nil {
			continue
		}
		content, err := os.ReadFile(path)
		if err != nil || len(content) == 0 || sha256Bytes(content) != expectedDigest {
			continue
		}
		covered[planID+"/"+taskID] = true
	}
	for _, raw := range requirements {
		requirement := stateObject(raw)
		if !covered[stateString(requirement["plan"])+"/"+stateString(requirement["task"])] {
			return false
		}
	}
	return true
}

func verificationOnlyMethodChangesSince(root, revision string) error {
	if _, err := workflowGit(root, "merge-base", "--is-ancestor", revision, "HEAD"); err != nil {
		return workflowError("STALE_EVIDENCE", "revisão do RC não é ancestral do HEAD atual")
	}
	changed, err := workflowGit(root, "diff", "--name-only", revision, "HEAD", "--")
	if err != nil {
		return workflowError("STALE_EVIDENCE", "não foi possível validar a revisão do RC")
	}
	for _, path := range nonEmptyLines(changed) {
		path = filepath.ToSlash(path)
		if path != ".bianchini" && !strings.HasPrefix(path, ".bianchini/") {
			return workflowError("STALE_EVIDENCE", "código mudou depois da criação do RC: "+path)
		}
	}
	return nil
}
