package gokernel

import (
	"bytes"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	learningIDPattern = regexp.MustCompile(`^L[0-9A-F]{12}$`)
	humanIDPattern    = regexp.MustCompile(`^human:[^\s:][^\s]*$`)
	learningClasses   = map[string]bool{
		"environment_fact": true, "human_preference": true, "repeatable_procedure": true,
		"deterministic_invariant": true, "architecture_decision": true, "isolated_error": true,
	}
	learningApprovable = map[string]bool{"repeatable_procedure": true, "deterministic_invariant": true}
	learningSuccess    = map[string]bool{"resolved": true, "completed": true, "passed": true, "accepted": true}
	learningValueFlags = map[string]bool{
		"--repo": true, "--since": true, "--candidate": true, "--digest": true,
		"--approved-by": true, "--reason": true,
	}
)

func runLearning(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if !oneOf(action, "propose", "list", "approve", "reject", "deactivate") {
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], learningValueFlags, map[string]bool{})
	if err != nil {
		return nil, err
	}
	switch action {
	case "approve":
		if lastValue(flags, "--candidate") == "" || lastValue(flags, "--digest") == "" || lastValue(flags, "--approved-by") == "" {
			return nil, userError("learn approve exige --candidate, --digest e --approved-by")
		}
	case "reject":
		if lastValue(flags, "--candidate") == "" || lastValue(flags, "--reason") == "" {
			return nil, userError("learn reject exige --candidate e --reason")
		}
	case "deactivate":
		if lastValue(flags, "--candidate") == "" || lastValue(flags, "--reason") == "" || lastValue(flags, "--approved-by") == "" {
			return nil, userError("learn deactivate exige --candidate, --reason e --approved-by")
		}
	}
	repo, err := learningRepo(lastValue(flags, "--repo"))
	if err != nil {
		return nil, err
	}
	switch action {
	case "propose":
		return learningPropose(repo, lastValue(flags, "--since"))
	case "list":
		return learningList(repo)
	case "approve":
		return learningApprove(repo, lastValue(flags, "--candidate"), lastValue(flags, "--digest"), lastValue(flags, "--approved-by"))
	case "reject":
		return learningReject(repo, lastValue(flags, "--candidate"), lastValue(flags, "--reason"))
	case "deactivate":
		return learningDeactivate(repo, lastValue(flags, "--candidate"), lastValue(flags, "--reason"), lastValue(flags, "--approved-by"))
	}
	return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
}

func learningRepo(value string) (string, error) {
	if value == "" {
		var err error
		value, err = os.Getwd()
		if err != nil {
			return "", learningError("LEARNING_PATH_INVALID", "repo Git obrigatório")
		}
	}
	abs, err := filepath.Abs(value)
	if err != nil || hasForeignPart(abs) {
		return "", learningError("LEARNING_PATH_INVALID", "raiz insegura")
	}
	if info, statErr := os.Lstat(abs); statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return "", learningError("LEARNING_PATH_INVALID", "raiz insegura")
	}
	resolved, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return "", learningError("LEARNING_PATH_INVALID", "raiz insegura")
	}
	command := exec.Command("git", "rev-parse", "--show-toplevel")
	command.Dir = abs
	output, err := command.CombinedOutput()
	if err != nil {
		return "", learningError("LEARNING_PATH_INVALID", "repo Git obrigatório")
	}
	top, err := filepath.EvalSymlinks(strings.TrimSpace(string(output)))
	if err != nil || filepath.Clean(top) != filepath.Clean(resolved) {
		return "", learningError("LEARNING_PATH_INVALID", "--repo deve apontar para a raiz Git")
	}
	return resolved, nil
}

func learningPropose(repo, since string) (map[string]any, error) {
	sources, err := learningSources(repo, since)
	if err != nil {
		return nil, err
	}
	candidates := make([]map[string]any, 0)
	for _, source := range sources {
		candidate, err := learningCandidate(repo, source)
		if err != nil {
			return nil, err
		}
		if candidate != nil {
			candidates = append(candidates, candidate)
		}
	}
	sort.Slice(candidates, func(i, j int) bool { return stateString(candidates[i]["id"]) < stateString(candidates[j]["id"]) })
	pending, err := learningFixedDir(repo, ".bianchini/.runtime/learning/pending", true)
	if err != nil {
		return nil, err
	}
	created := 0
	results := make([]any, 0, len(candidates))
	for _, candidate := range candidates {
		id := stateString(candidate["id"])
		path := filepath.Join(pending, id+".json")
		content, _ := learningCanonical(candidate)
		if info, statErr := os.Lstat(path); statErr == nil {
			if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
				return nil, learningError("STALE_EVIDENCE", "candidato divergente: "+id)
			}
			existing, readErr := os.ReadFile(path)
			if readErr != nil || !bytes.Equal(existing, content) {
				return nil, learningError("STALE_EVIDENCE", "candidato divergente: "+id)
			}
		} else if os.IsNotExist(statErr) {
			if err := learningAtomicWrite(repo, path, content); err != nil {
				return nil, err
			}
			created++
		} else {
			return nil, learningError("LEARNING_PATH_INVALID", statErr.Error())
		}
		relative, _ := filepath.Rel(repo, path)
		results = append(results, map[string]any{
			"id": id, "digest": candidate["digest"], "classification": candidate["classification"], "path": filepath.ToSlash(relative),
		})
	}
	var sinceValue any
	if since != "" {
		sinceValue = since
	}
	return map[string]any{"status": "proposed", "created": created, "candidates": results, "since": sinceValue}, nil
}

func learningCandidate(repo, source string) (map[string]any, error) {
	payload, present, err := learningFrontmatter(source)
	if err != nil {
		return nil, err
	}
	if !present || payload["learning_candidate"] == nil {
		return nil, nil
	}
	raw, ok := payload["learning_candidate"].(map[string]any)
	if !ok {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "learning_candidate exige objeto")
	}
	allowed := map[string]bool{"classification": true, "statement": true, "tags": true, "validity": true, "conflicts": true}
	unknown := make([]string, 0)
	for key := range raw {
		if !allowed[key] {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "campo desconhecido: "+unknown[0])
	}
	classification := stateString(raw["classification"])
	if !learningClasses[classification] {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "classification inválida")
	}
	if classification == "isolated_error" {
		return nil, nil
	}
	if !learningSuccess[stateString(payload["status"])] || strings.TrimSpace(stateString(payload["green"])) == "" {
		return nil, learningError("LEARNING_EVIDENCE_REQUIRED", "somente fonte terminal com sucesso comprovado pode propor aprendizado")
	}
	evidenceValue := payload["evidence"]
	if evidenceValue == nil {
		evidenceValue = payload["verification"]
	}
	if evidenceValue == nil {
		events := stateArray(payload["events"])
		derived := make([]any, 0)
		for _, item := range events {
			if text := strings.TrimSpace(stateString(stateObject(item)["evidence"])); text != "" {
				derived = append(derived, text)
			}
		}
		evidenceValue = derived
	}
	evidence, err := learningTextList(evidenceValue, "evidence", true)
	if err != nil {
		return nil, err
	}
	statement, validity := strings.TrimSpace(stateString(raw["statement"])), strings.TrimSpace(stateString(raw["validity"]))
	if statement == "" {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "statement obrigatório")
	}
	if validity == "" {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "validity obrigatória")
	}
	tags, err := learningTextList(raw["tags"], "tags", true)
	if err != nil {
		return nil, err
	}
	conflicts, err := learningTextList(raw["conflicts"], "conflicts", false)
	if err != nil {
		return nil, err
	}
	content, err := os.ReadFile(source)
	if err != nil {
		return nil, learningError("LEARNING_SOURCE_INVALID", filepath.Base(source)+": "+err.Error())
	}
	relative, _ := filepath.Rel(repo, source)
	base := map[string]any{
		"schema_version": 1, "status": "pending", "classification": classification,
		"statement": statement, "tags": tags, "validity": validity, "conflicts": conflicts,
		"evidence": evidence, "source": filepath.ToSlash(relative), "source_digest": sha256Bytes(content),
	}
	baseDigest := learningDigest(base)
	id := "L" + strings.ToUpper(baseDigest[:12])
	candidate := cloneMap(base)
	candidate["id"] = id
	candidate["digest"] = learningDigest(candidate)
	return candidate, nil
}

func learningApprove(repo, id, digest, approvedBy string) (map[string]any, error) {
	if !humanIDPattern.MatchString(approvedBy) {
		return nil, learningError("HUMAN_APPROVAL_REQUIRED", "approved_by exige identidade human:<id>")
	}
	source, candidate, err := loadLearningCandidate(repo, id)
	if err != nil {
		return nil, err
	}
	if stateString(candidate["digest"]) != digest {
		return nil, learningError("STALE_EVIDENCE", "digest informado não corresponde ao candidato")
	}
	if !learningApprovable[stateString(candidate["classification"])] {
		return nil, learningError("LEARNING_DESTINATION_REQUIRED", "classificação pertence a outro mecanismo de verdade")
	}
	original, err := learningSafeSource(repo, stateString(candidate["source"]))
	if err != nil {
		return nil, err
	}
	sources, err := learningSources(repo, "")
	if err != nil {
		return nil, err
	}
	if !containsString(sources, original) {
		return nil, learningError("LEARNING_PATH_INVALID", "source não pertence ao conjunto governado")
	}
	content, err := os.ReadFile(original)
	if err != nil || sha256Bytes(content) != stateString(candidate["source_digest"]) {
		return nil, learningError("STALE_EVIDENCE", "fonte do candidato mudou")
	}
	expected, err := learningCandidate(repo, original)
	if err != nil {
		return nil, err
	}
	expectedJSON, _ := learningCanonical(expected)
	candidateJSON, _ := learningCanonical(candidate)
	if expected == nil || !bytes.Equal(expectedJSON, candidateJSON) {
		return nil, learningError("STALE_EVIDENCE", "candidato não deriva da fonte governada atual")
	}
	approved := cloneMap(candidate)
	delete(approved, "digest")
	approved["status"] = "approved"
	approved["active"] = true
	approved["approved_by"] = approvedBy
	approved["approved_digest"] = digest
	approved["approved_at"] = utcNow()
	lessons, err := learningFixedDir(repo, ".bianchini/current/lessons", true)
	if err != nil {
		return nil, err
	}
	target := filepath.Join(lessons, id+".json")
	if _, err := os.Lstat(target); err == nil {
		return nil, learningError("STALE_EVIDENCE", "lição já existe: "+id)
	}
	encoded, _ := learningCanonical(approved)
	if err := learningAtomicWrite(repo, target, encoded); err != nil {
		return nil, err
	}
	if err := os.Remove(source); err != nil {
		return nil, learningError("LEARNING_PATH_INVALID", err.Error())
	}
	relative, _ := filepath.Rel(repo, target)
	return map[string]any{"id": id, "status": "approved", "path": filepath.ToSlash(relative), "digest": digest}, nil
}

func learningDeactivate(repo, id, reason, actor string) (map[string]any, error) {
	if !learningIDPattern.MatchString(id) {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", "ID de lição inválido")
	}
	if strings.TrimSpace(reason) == "" {
		return nil, learningError("LEARNING_DEACTIVATION_INVALID", "desativação exige motivo")
	}
	if !humanIDPattern.MatchString(actor) {
		return nil, learningError("HUMAN_APPROVAL_REQUIRED", "deactivated_by exige identidade human:<id>")
	}
	lessons, err := learningFixedDir(repo, ".bianchini/current/lessons", false)
	if err != nil {
		return nil, err
	}
	path := filepath.Join(lessons, id+".json")
	value, raw, err := learningJSONObject(path, "lição")
	if err != nil {
		return nil, err
	}
	canonical, _ := learningCanonical(value)
	if !bytes.Equal(canonical, raw) {
		return nil, learningError("STALE_EVIDENCE", "lição não está em forma canônica")
	}
	if stateString(value["id"]) != id || stateString(value["status"]) != "approved" || value["active"] == false || stateString(value["approved_by"]) == "" || stateString(value["approved_digest"]) == "" {
		return nil, learningError("STALE_EVIDENCE", "lição aprovada possui estado inválido")
	}
	value["active"] = false
	value["deactivated_by"] = actor
	value["deactivated_at"] = utcNow()
	value["deactivation_reason"] = strings.TrimSpace(reason)
	encoded, _ := learningCanonical(value)
	if err := learningAtomicWrite(repo, path, encoded); err != nil {
		return nil, err
	}
	relative, _ := filepath.Rel(repo, path)
	return map[string]any{"id": id, "status": "approved", "active": false, "path": filepath.ToSlash(relative)}, nil
}

func learningReject(repo, id, reason string) (map[string]any, error) {
	if strings.TrimSpace(reason) == "" {
		return nil, learningError("LEARNING_REJECTION_INVALID", "rejeição exige motivo")
	}
	source, candidate, err := loadLearningCandidate(repo, id)
	if err != nil {
		return nil, err
	}
	candidate["status"] = "rejected"
	candidate["rejection_reason"] = strings.TrimSpace(reason)
	candidate["rejected_at"] = utcNow()
	directory, err := learningFixedDir(repo, ".bianchini/.runtime/learning/rejected", true)
	if err != nil {
		return nil, err
	}
	target := filepath.Join(directory, id+".json")
	if _, err := os.Lstat(target); err == nil {
		return nil, learningError("STALE_EVIDENCE", "rejeição já existe: "+id)
	}
	encoded, _ := learningCanonical(candidate)
	if err := learningAtomicWrite(repo, target, encoded); err != nil {
		return nil, err
	}
	if err := os.Remove(source); err != nil {
		return nil, learningError("LEARNING_PATH_INVALID", err.Error())
	}
	relative, _ := filepath.Rel(repo, target)
	return map[string]any{"id": id, "status": "rejected", "path": filepath.ToSlash(relative)}, nil
}

func learningList(repo string) (map[string]any, error) {
	pending, err := learningListed(repo, ".bianchini/.runtime/learning/pending")
	if err != nil {
		return nil, err
	}
	rejected, err := learningListed(repo, ".bianchini/.runtime/learning/rejected")
	if err != nil {
		return nil, err
	}
	approved, err := learningListed(repo, ".bianchini/current/lessons")
	if err != nil {
		return nil, err
	}
	return map[string]any{"pending": pending, "rejected": rejected, "approved": approved}, nil
}

func loadLearningCandidate(repo, id string) (string, map[string]any, error) {
	if !learningIDPattern.MatchString(id) {
		return "", nil, learningError("LEARNING_CANDIDATE_INVALID", "ID de candidato inválido")
	}
	pending, err := learningFixedDir(repo, ".bianchini/.runtime/learning/pending", false)
	if err != nil {
		return "", nil, err
	}
	path := filepath.Join(pending, id+".json")
	value, raw, err := learningJSONObject(path, "candidato")
	if err != nil {
		if strings.Contains(err.Error(), "ausente") {
			return "", nil, learningError("LEARNING_CANDIDATE_INVALID", "candidato ausente: "+id)
		}
		return "", nil, err
	}
	canonical, _ := learningCanonical(value)
	if !bytes.Equal(canonical, raw) {
		return "", nil, learningError("STALE_EVIDENCE", "candidato não está em forma canônica")
	}
	storedDigest := stateString(value["digest"])
	unsigned := cloneMap(value)
	delete(unsigned, "digest")
	if storedDigest != learningDigest(unsigned) {
		return "", nil, learningError("STALE_EVIDENCE", "digest interno do candidato divergiu")
	}
	expectedKeys := []string{"classification", "conflicts", "digest", "evidence", "id", "schema_version", "source", "source_digest", "statement", "status", "tags", "validity"}
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	if strings.Join(keys, "\x00") != strings.Join(expectedKeys, "\x00") || stateInt(value["schema_version"]) != 1 {
		return "", nil, learningError("STALE_EVIDENCE", "schema do candidato divergiu")
	}
	if stateString(value["status"]) != "pending" || !learningClasses[stateString(value["classification"])] {
		return "", nil, learningError("STALE_EVIDENCE", "estado do candidato divergiu")
	}
	base := cloneMap(unsigned)
	delete(base, "id")
	expectedID := "L" + strings.ToUpper(learningDigest(base)[:12])
	if stateString(value["id"]) != id || expectedID != id {
		return "", nil, learningError("STALE_EVIDENCE", "ID não deriva do conteúdo do candidato")
	}
	for _, field := range []string{"tags", "conflicts", "evidence"} {
		if _, err := learningTextList(value[field], field, field != "conflicts"); err != nil {
			return "", nil, err
		}
	}
	for _, field := range []string{"statement", "validity", "source"} {
		if strings.TrimSpace(stateString(value[field])) == "" {
			return "", nil, learningError("STALE_EVIDENCE", field+" inválido no candidato")
		}
	}
	if !hexDigestPattern.MatchString(stateString(value["source_digest"])) {
		return "", nil, learningError("STALE_EVIDENCE", "source_digest inválido no candidato")
	}
	return path, value, nil
}

func learningSources(repo, since string) ([]string, error) {
	allowed := map[string]bool(nil)
	if since != "" {
		if _, err := workflowGit(repo, "rev-parse", "--verify", since+"^{commit}"); err != nil {
			return nil, learningError("LEARNING_SINCE_INVALID", "ref inexistente: "+since)
		}
		changed, err := workflowGit(repo, "diff", "--name-only", since+"..HEAD", "--", ".bianchini")
		if err != nil {
			return nil, learningError("LEARNING_SINCE_INVALID", err.Error())
		}
		allowed = map[string]bool{}
		for _, path := range nonEmptyLines(changed) {
			allowed[path] = true
		}
	}
	if _, err := learningFixedDir(repo, ".bianchini", false); err != nil {
		if os.IsNotExist(err) {
			return []string{}, nil
		}
		return nil, err
	}
	set := map[string]bool{}
	add := func(path string) error {
		relative, _ := filepath.Rel(repo, path)
		relative = filepath.ToSlash(relative)
		if hasForeignPart(relative) {
			return nil
		}
		info, err := os.Lstat(path)
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return learningError("LEARNING_PATH_INVALID", err.Error())
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return learningError("LEARNING_PATH_INVALID", "fonte symlink: "+relative)
		}
		if info.Mode().IsRegular() && (allowed == nil || allowed[relative]) {
			set[path] = true
		}
		return nil
	}
	resolved, err := learningFixedDir(repo, ".bianchini/debug/resolved", false)
	if err != nil {
		return nil, err
	}
	if entries, readErr := os.ReadDir(resolved); readErr == nil {
		for _, entry := range entries {
			if strings.HasSuffix(entry.Name(), ".md") {
				if err := add(filepath.Join(resolved, entry.Name())); err != nil {
					return nil, err
				}
			}
		}
	}
	if err := add(filepath.Join(repo, ".bianchini", "debug", "KNOWLEDGE.md")); err != nil {
		return nil, err
	}
	for _, area := range []string{"changes", "archive"} {
		directory, err := learningFixedDir(repo, ".bianchini/"+area, false)
		if err != nil {
			return nil, err
		}
		entries, readErr := os.ReadDir(directory)
		if readErr != nil {
			continue
		}
		for _, entry := range entries {
			if entry.Type()&os.ModeSymlink != 0 {
				return nil, learningError("LEARNING_PATH_INVALID", "diretório symlink: .bianchini/"+area+"/"+entry.Name())
			}
			if !entry.IsDir() || strings.EqualFold(entry.Name(), ".planning") {
				continue
			}
			work := filepath.Join(directory, entry.Name())
			if err := add(filepath.Join(work, "COHERENCE.md")); err != nil {
				return nil, err
			}
			results := filepath.Join(work, "results")
			walkErr := filepath.WalkDir(results, func(path string, child fs.DirEntry, err error) error {
				if err != nil {
					if os.IsNotExist(err) {
						return nil
					}
					return err
				}
				if child.Type()&os.ModeSymlink != 0 {
					return learningError("LEARNING_PATH_INVALID", "diretório symlink: "+filepath.ToSlash(path))
				}
				if child.IsDir() && strings.EqualFold(child.Name(), ".planning") {
					return filepath.SkipDir
				}
				if !child.IsDir() && strings.HasSuffix(child.Name(), ".md") {
					return add(path)
				}
				return nil
			})
			if walkErr != nil && !os.IsNotExist(walkErr) {
				return nil, walkErr
			}
		}
	}
	result := make([]string, 0, len(set))
	for path := range set {
		result = append(result, path)
	}
	sort.Strings(result)
	return result, nil
}

func learningListed(repo, relative string) ([]any, error) {
	directory, err := learningFixedDir(repo, relative, false)
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		if os.IsNotExist(err) {
			return []any{}, nil
		}
		return nil, learningError("LEARNING_PATH_INVALID", err.Error())
	}
	result := make([]any, 0)
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), "L") || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if entry.Type()&os.ModeSymlink != 0 || entry.IsDir() {
			return nil, learningError("LEARNING_PATH_INVALID", "entrada insegura: "+entry.Name())
		}
		value, _, err := learningJSONObject(path, "entrada")
		if err != nil {
			return nil, err
		}
		digest := stateString(value["digest"])
		if digest == "" {
			digest = stateString(value["approved_digest"])
		}
		relativePath, _ := filepath.Rel(repo, path)
		result = append(result, map[string]any{
			"id": value["id"], "status": value["status"], "classification": value["classification"],
			"path": filepath.ToSlash(relativePath), "digest": digest,
		})
	}
	return result, nil
}

func learningFixedDir(repo, relative string, create bool) (string, error) {
	path := repo
	for _, part := range strings.Split(filepath.FromSlash(relative), string(filepath.Separator)) {
		if part == "" || strings.EqualFold(part, ".planning") {
			return "", learningError("LEARNING_PATH_INVALID", "diretório inválido: "+relative)
		}
		path = filepath.Join(path, part)
		info, err := os.Lstat(path)
		if err == nil {
			if info.Mode()&os.ModeSymlink != 0 {
				return "", learningError("LEARNING_PATH_INVALID", "symlink não permitido: "+relative)
			}
			if !info.IsDir() {
				return "", learningError("LEARNING_PATH_INVALID", "diretório inválido: "+relative)
			}
			continue
		}
		if !os.IsNotExist(err) {
			return "", learningError("LEARNING_PATH_INVALID", err.Error())
		}
		if !create {
			return path, nil
		}
		if err := os.Mkdir(path, 0o755); err != nil {
			return "", learningError("LEARNING_PATH_INVALID", err.Error())
		}
	}
	return path, nil
}

func learningAtomicWrite(repo, path string, content []byte) error {
	relative, err := filepath.Rel(filepath.Join(repo, ".bianchini"), path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || hasForeignPart(relative) {
		return learningError("LEARNING_PATH_INVALID", "escrita fora de .bianchini")
	}
	workspace := newMethodWorkspace(repo)
	if err := workspace.atomicWrite(path, content); err != nil {
		return learningError("LEARNING_PATH_INVALID", strings.TrimPrefix(err.Error(), "MODEL_MISMATCH: "))
	}
	return nil
}

func learningSafeSource(repo, relative string) (string, error) {
	if relative == "" || strings.Contains(relative, "\\") || filepath.IsAbs(relative) || filepath.ToSlash(filepath.Clean(relative)) != relative || hasForeignPart(relative) {
		return "", learningError("LEARNING_PATH_INVALID", "source deve ser path relativo confinado")
	}
	path := repo
	for _, part := range strings.Split(relative, "/") {
		path = filepath.Join(path, part)
		if info, err := os.Lstat(path); err == nil && info.Mode()&os.ModeSymlink != 0 {
			return "", learningError("LEARNING_PATH_INVALID", "source não aceita symlink")
		}
	}
	if !regularFile(path) {
		return "", learningError("STALE_EVIDENCE", "fonte do candidato desapareceu")
	}
	return path, nil
}

func learningJSONObject(path, label string) (map[string]any, []byte, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, nil, learningError("LEARNING_PATH_INVALID", label+" ausente ou inseguro")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, learningError("LEARNING_SOURCE_INVALID", filepath.Base(path)+": "+err.Error())
	}
	value, err := decodeJSONObject(raw)
	if err != nil {
		return nil, nil, learningError("STALE_EVIDENCE", label+" corrompido: "+err.Error())
	}
	return value, raw, nil
}

func learningFrontmatter(path string) (map[string]any, bool, error) {
	info, err := os.Lstat(path)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return nil, false, learningError("LEARNING_PATH_INVALID", "fonte governada inválida")
	}
	content, err := os.ReadFile(path)
	if err != nil || !validUTF8Text(content) {
		return nil, false, learningError("LEARNING_SOURCE_INVALID", filepath.Base(path)+": conteúdo inválido")
	}
	if !bytes.HasPrefix(content, []byte("---\n")) {
		return nil, false, nil
	}
	match := frontmatterPattern.FindSubmatch(content)
	if match == nil {
		return nil, false, learningError("LEARNING_SOURCE_INVALID", filepath.Base(path)+": frontmatter inválido")
	}
	value, err := decodeJSONObject(match[1])
	if err != nil {
		return nil, false, learningError("LEARNING_SOURCE_INVALID", filepath.Base(path)+": "+err.Error())
	}
	return value, true, nil
}

func learningTextList(value any, label string, required bool) ([]string, error) {
	if required && value == nil {
		return nil, learningError("LEARNING_EVIDENCE_REQUIRED", label+" obrigatório")
	}
	values, ok := value.([]any)
	if !ok {
		return nil, learningError("LEARNING_CANDIDATE_INVALID", label+" exige lista de textos")
	}
	result := make([]string, 0, len(values))
	seen := map[string]bool{}
	for _, raw := range values {
		text, ok := raw.(string)
		text = strings.TrimSpace(text)
		if !ok || text == "" {
			return nil, learningError("LEARNING_CANDIDATE_INVALID", label+" exige lista de textos")
		}
		if !seen[text] {
			seen[text] = true
			result = append(result, text)
		}
	}
	if required && len(result) == 0 {
		return nil, learningError("LEARNING_EVIDENCE_REQUIRED", label+" não pode ser vazio")
	}
	return result, nil
}

func learningCanonical(value map[string]any) ([]byte, error) {
	encoded, err := canonicalJSON(value)
	if err != nil {
		return nil, err
	}
	return append(encoded, '\n'), nil
}

func learningDigest(value map[string]any) string {
	encoded, _ := learningCanonical(value)
	return sha256Bytes(encoded)
}

func learningError(code, message string) error {
	return &commandError{message: code + ": " + message, exitCode: 3}
}

func hasForeignPart(path string) bool {
	for _, part := range strings.FieldsFunc(filepath.ToSlash(path), func(r rune) bool { return r == '/' }) {
		if strings.EqualFold(part, ".planning") || part == ".." || part == "." || part == "" {
			return true
		}
	}
	return false
}
