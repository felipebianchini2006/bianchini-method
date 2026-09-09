package gokernel

import (
	"context"
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

	methodlayout "github.com/felipebianchini2006/bianchini-method/internal/workspace"
)

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
		if oneOf(request.scope, "quick", "debug") {
			head = "UNBORN"
		} else {
			return nil, err
		}
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
		"candidate_fingerprint": request.candidateDigest, "candidate": request.candidate,
		"scope": request.scope, "change": filepath.Base(request.pack.directory), "plan": request.plan,
		"task": nullableString(request.task), "unit": request.unit, "kind": spec.kind,
		"risk_seam":    request.seam,
		"cache_policy": spec.cache, "argv": stringSliceAny(spec.argv), "cwd": spec.cwd, "timeout_seconds": spec.timeout,
		"proves": spec.proves, "source_revision": head,
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
	if len(existing) > 0 {
		proof := existing[len(existing)-1]
		if spec.cache == "deterministic" && stateString(proof["status"]) == "passed" {
			return map[string]any{"proof_id": proof["proof_id"], "status": "passed", "reused": true, "proof": proof}, nil
		}
	}
	if len(existing) > 0 && stateString(existing[len(existing)-1]["status"]) == "failed" && strings.TrimSpace(request.retryReason) == "" {
		return nil, workflowError("VERIFICATION_RETRY_REQUIRED", "a mesma verificação já falhou neste estado; informe --retry-reason para repetir")
	}
	policy, sequence, err := verificationAttemptPolicy(request, fingerprint)
	if err != nil {
		return nil, err
	}
	attempt := len(existing) + 1
	started := utcNow()
	exitCode, timedOut, spawnError := 0, false, false
	outputTruncated := false
	stdout, stderr := []byte{}, []byte{}
	if spec.kind != "procedure" {
		cwd, cwdErr := verificationCWD(request.pack.workspace.root, spec.cwd)
		if cwdErr != nil {
			return nil, cwdErr
		}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(spec.timeout)*time.Second)
		command := exec.CommandContext(ctx, spec.argv[0], spec.argv[1:]...)
		command.Dir = cwd
		if request.candidate != nil {
			command.Env = append(os.Environ(), "BM_CANDIDATE_BUILD="+stateString(request.candidate["build"]), "BM_CANDIDATE_CHECKSUM="+stateString(request.candidate["checksum"]))
		}
		var stdoutBuffer, stderrBuffer verificationOutput
		command.Stdout, command.Stderr = &stdoutBuffer, &stderrBuffer
		runErr := command.Run()
		cancel()
		stdout, stderr = stdoutBuffer.Bytes(), stderrBuffer.Bytes()
		outputTruncated = stdoutBuffer.truncated || stderrBuffer.truncated
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
	record["execution_sequence"] = sequence
	record["policy"] = policy
	record["fix_round"] = policy["fix_round"]
	record["retry_reason"] = nullableString(strings.TrimSpace(request.retryReason))
	record["exit_code"] = exitCode
	record["timed_out"] = timedOut
	record["spawn_error"] = spawnError
	record["output_truncated"] = outputTruncated
	record["stdout_sha256"] = sha256Bytes(stdout)
	record["stderr_sha256"] = sha256Bytes(stderr)
	record["evidence_path"] = evidencePath
	record["evidence_sha256"] = evidenceDigest
	record["stdout_summary"] = sanitizeVerificationOutput(stdout)
	record["stderr_summary"] = sanitizeVerificationOutput(stderr)
	record["status"] = status
	record["started_at"] = started
	record["finished_at"] = utcNow()
	idMaterial := cloneMap(record)
	delete(idMaterial, "started_at")
	delete(idMaterial, "finished_at")
	proofID := "proof-" + waveStableDigest(idMaterial)[:32]
	record["proof_id"] = proofID
	logPath := filepath.Join(methodlayout.Logs(request.pack.directory), proofID+".log")
	logText := stateString(record["stdout_summary"]) + "\n" + stateString(record["stderr_summary"])
	if outputTruncated {
		logText += "\n[output truncated at 256 KiB per stream]\n"
	}
	if err := request.pack.workspace.atomicWrite(logPath, []byte(logText)); err != nil {
		return nil, err
	}
	relativeLog, _ := filepath.Rel(request.pack.directory, logPath)
	record["log_path"], record["log_sha256"] = filepath.ToSlash(relativeLog), sha256Bytes([]byte(logText))
	for _, key := range []string{"stdout_summary", "stderr_summary"} {
		text := stateString(record[key])
		if len(text) > 4096 {
			record[key] = text[:4096] + "\n[output truncated; see log]"
		}
	}
	record["record_digest"] = verificationRecordDigest(record)
	path := filepath.Join(methodlayout.Proofs(request.pack.directory), proofID+".json")
	encoded, _ := json.MarshalIndent(record, "", "  ")
	if err := request.pack.workspace.atomicWrite(path, append(encoded, '\n')); err != nil {
		return nil, err
	}
	if err := writePlanEvidenceIndex(request.pack, request.plan); err != nil {
		return nil, err
	}
	if status != "passed" {
		return map[string]any{"proof_id": proofID, "status": status, "reused": false, "proof": record}, workflowError("VERIFICATION_FAILED", fmt.Sprintf("%s falhou com exit code %d; proof_id %s", request.unit, exitCode, proofID))
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
