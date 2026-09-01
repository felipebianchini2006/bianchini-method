package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

var contextDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

func contextLessonSelectors(unit string, context map[string]any) map[string]bool {
	selectors := map[string]bool{unit: true}
	if plan, ok := context["plan"].(map[string]any); ok {
		for _, field := range []string{"requirements", "provides", "consumes", "modules", "interfaces", "data"} {
			for value := range contextStringSet(plan[field]) {
				selectors[value] = true
			}
		}
	}
	if task, ok := context["task"].(map[string]any); ok {
		for _, field := range []string{"covers", "files"} {
			for value := range contextStringSet(task[field]) {
				selectors[value] = true
			}
		}
		if riskSeam, ok := task["risk_seam"].(string); ok {
			selectors[riskSeam] = true
		}
	}
	for _, name := range []string{"brief", "debug", "release_candidate"} {
		value, ok := context[name].(map[string]any)
		if !ok {
			continue
		}
		for _, field := range []string{"scope", "requirements", "paths", "contracts", "seams", "tags"} {
			for item := range contextStringSet(value[field]) {
				selectors[item] = true
			}
		}
	}
	return selectors
}

func contextLessonTags(value map[string]any) map[string]bool {
	result := map[string]bool{}
	switch tags := value["tags"].(type) {
	case []any:
		for _, item := range tags {
			if text, ok := item.(string); ok {
				result[text] = true
			}
		}
	case map[string]any:
		for _, raw := range tags {
			if text, ok := raw.(string); ok {
				result[text] = true
			} else {
				for item := range contextStringSet(raw) {
					result[item] = true
				}
			}
		}
	}
	return result
}

func contextApprovedLessons(root string, reader *contextSourceReader, unit string, context map[string]any, required map[string]bool) ([]any, error) {
	directory := filepath.Join(root, ".bianchini", "current", "lessons")
	if _, err := os.Lstat(directory); os.IsNotExist(err) {
		return []any{}, nil
	}
	children, err := contextChildren(directory, "lições aprovadas")
	if err != nil {
		return nil, err
	}
	selectors := contextLessonSelectors(unit, context)
	selected := make([]map[string]any, 0)
	selectedIDs := map[string]bool{}
	for _, path := range children {
		info, statErr := os.Lstat(path)
		if statErr != nil || !info.Mode().IsRegular() || (filepath.Ext(path) != ".json" && filepath.Ext(path) != ".md") {
			continue
		}
		var value map[string]any
		if filepath.Ext(path) == ".json" {
			value, err = reader.jsonObject(path, "lição "+filepath.Base(path))
		} else {
			value, err = reader.frontmatter(path, "lição "+filepath.Base(path))
		}
		if err != nil {
			return nil, err
		}
		if stateString(value["status"]) != "approved" || value["active"] == false {
			continue
		}
		identifier, ok := value["id"].(string)
		if !ok || !learningIDPattern.MatchString(identifier) {
			return nil, contextError("PACK_INCOMPLETE", "lição aprovada possui id inválido: "+filepath.Base(path))
		}
		approvedBy, approvedByOK := value["approved_by"].(string)
		if !approvedByOK || !humanIDPattern.MatchString(approvedBy) {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" não possui aprovação humana")
		}
		approvedDigest, digestOK := value["approved_digest"].(string)
		if !digestOK || !contextDigestPattern.MatchString(approvedDigest) {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" possui digest de aprovação inválido")
		}
		candidate := map[string]any{}
		for key, item := range value {
			switch key {
			case "active", "approved_by", "approved_digest", "approved_at":
				continue
			default:
				candidate[key] = item
			}
		}
		candidate["status"] = "pending"
		candidateBytes, _ := contextCanonical(candidate)
		base := map[string]any{}
		for key, item := range candidate {
			if key != "id" {
				base[key] = item
			}
		}
		baseBytes, _ := contextCanonical(base)
		expectedID := "L" + strings.ToUpper(sha256Bytes(baseBytes)[:12])
		if sha256Bytes(candidateBytes) != approvedDigest || expectedID != identifier {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" não deriva de candidato aprovado")
		}
		sourceValue, sourceOK := value["source"].(string)
		sourceDigest, sourceDigestOK := value["source_digest"].(string)
		if !sourceOK || !sourceDigestOK || !contextDigestPattern.MatchString(sourceDigest) {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" não possui fonte")
		}
		if !contextSetsIntersect(contextLessonTags(value), selectors) {
			continue
		}
		sourceCandidates := []string{sourceValue}
		parts := strings.Split(sourceValue, "/")
		if len(parts) >= 4 && parts[0] == ".bianchini" && parts[1] == "changes" {
			sourceCandidates = append(sourceCandidates, filepath.ToSlash(filepath.Join(".bianchini", "archive", filepath.Join(parts[2:]...))))
		}
		existing := make([]string, 0)
		for index, raw := range sourceCandidates {
			label := "lesson:" + identifier + ".source"
			if index > 0 {
				label = "lesson:" + identifier + ".archive_source"
			}
			candidatePath, safeErr := contextSafePath(root, raw, label)
			if safeErr != nil {
				return nil, safeErr
			}
			if info, statErr := os.Lstat(candidatePath); statErr == nil && info.Mode().IsRegular() && info.Mode()&os.ModeSymlink == 0 {
				existing = append(existing, candidatePath)
			}
		}
		if len(existing) != 1 {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" exige uma fonte histórica íntegra")
		}
		source := existing[0]
		sourceBytes, readErr := reader.bytes(source, "lesson:"+identifier+".source")
		if readErr != nil {
			return nil, readErr
		}
		if sha256Bytes(sourceBytes) != sourceDigest {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" possui fonte alterada")
		}
		expectedCandidate, candidateErr := contextCandidateFromSource(root, source, sourceValue, sourceBytes)
		if candidateErr != nil {
			code := strings.SplitN(candidateErr.Error(), ":", 2)[0]
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" não deriva de fonte governada ("+code+")")
		}
		if expectedCandidate != nil {
			expectedBase := map[string]any{}
			for key, item := range expectedCandidate {
				if key != "id" && key != "digest" {
					expectedBase[key] = item
				}
			}
			expectedBase["source"] = sourceValue
			expectedBaseBytes, _ := contextCanonical(expectedBase)
			expectedCandidate = cloneMap(expectedBase)
			expectedCandidate["id"] = "L" + strings.ToUpper(sha256Bytes(expectedBaseBytes)[:12])
			expectedWithID, _ := contextCanonical(expectedCandidate)
			expectedCandidate["digest"] = sha256Bytes(expectedWithID)
		}
		actualCandidate := cloneMap(candidate)
		actualCandidate["digest"] = approvedDigest
		expectedJSON, _ := contextCanonical(expectedCandidate)
		actualJSON, _ := contextCanonical(actualCandidate)
		if expectedCandidate == nil || !bytes.Equal(expectedJSON, actualJSON) {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+identifier+" diverge da proposta da fonte")
		}
		selected = append(selected, value)
		selectedIDs[identifier] = true
		required["lesson:"+identifier] = true
	}
	for _, lesson := range selected {
		conflicts, ok := lesson["conflicts"].([]any)
		if !ok {
			return nil, contextError("PACK_INCOMPLETE", "lesson:"+stateString(lesson["id"])+" possui conflicts inválido")
		}
		active := make([]string, 0)
		for _, raw := range conflicts {
			value, valid := raw.(string)
			if !valid {
				return nil, contextError("PACK_INCOMPLETE", "lesson:"+stateString(lesson["id"])+" possui conflicts inválido")
			}
			if selectedIDs[value] {
				active = append(active, value)
			}
		}
		sort.Strings(active)
		if len(active) > 0 {
			return nil, contextError("PACK_INCOMPLETE", "lições relevantes conflitam: "+stateString(lesson["id"])+" x "+strings.Join(active, ", "))
		}
	}
	sort.Slice(selected, func(i, j int) bool { return stateString(selected[i]["id"]) < stateString(selected[j]["id"]) })
	result := make([]any, len(selected))
	for index := range selected {
		result[index] = selected[index]
	}
	return result, nil
}

func contextCandidateFromSource(root, source, sourceIdentity string, sourceBytes []byte) (map[string]any, error) {
	if !utf8.Valid(sourceBytes) || !bytes.HasPrefix(sourceBytes, []byte("---\n")) {
		return nil, contextError("LEARNING_SOURCE_INVALID", filepath.Base(source)+": conteúdo inválido")
	}
	match := frontmatterPattern.FindSubmatch(sourceBytes)
	if match == nil {
		return nil, contextError("LEARNING_SOURCE_INVALID", filepath.Base(source)+": frontmatter inválido")
	}
	var payload map[string]any
	if err := json.Unmarshal(match[1], &payload); err != nil {
		return nil, contextError("LEARNING_SOURCE_INVALID", filepath.Base(source)+": "+err.Error())
	}
	rawCandidate := payload["learning_candidate"]
	if rawCandidate == nil {
		return nil, nil
	}
	raw, ok := rawCandidate.(map[string]any)
	if !ok {
		return nil, contextError("LEARNING_CANDIDATE_INVALID", "learning_candidate exige objeto")
	}
	allowed := map[string]bool{"classification": true, "statement": true, "tags": true, "validity": true, "conflicts": true}
	unknown := make([]string, 0)
	for field := range raw {
		if !allowed[field] {
			unknown = append(unknown, field)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return nil, contextError("LEARNING_CANDIDATE_INVALID", "campo desconhecido: "+unknown[0])
	}
	classification := stateString(raw["classification"])
	classes := map[string]bool{
		"environment_fact": true, "human_preference": true, "repeatable_procedure": true,
		"deterministic_invariant": true, "architecture_decision": true, "isolated_error": true,
	}
	if !classes[classification] {
		return nil, contextError("LEARNING_CANDIDATE_INVALID", "classification inválida")
	}
	if classification == "isolated_error" {
		return nil, nil
	}
	success := map[string]bool{"resolved": true, "completed": true, "passed": true, "accepted": true}
	if !success[stateString(payload["status"])] || !contextTruthy(payload["green"]) {
		return nil, contextError("LEARNING_EVIDENCE_REQUIRED", "somente fonte terminal com sucesso comprovado pode propor aprendizado")
	}
	evidenceValue := payload["evidence"]
	if evidenceValue == nil {
		evidenceValue = payload["verification"]
	}
	if evidenceValue == nil {
		derived := make([]any, 0)
		if events, ok := payload["events"].([]any); ok {
			for _, rawEvent := range events {
				if text := strings.TrimSpace(stateString(stateObject(rawEvent)["evidence"])); text != "" {
					derived = append(derived, text)
				}
			}
		}
		evidenceValue = derived
	}
	evidence, err := contextLearningTextList(evidenceValue, "evidence", true)
	if err != nil {
		return nil, err
	}
	statement := strings.TrimSpace(stateString(raw["statement"]))
	validity := strings.TrimSpace(stateString(raw["validity"]))
	if statement == "" {
		return nil, contextError("LEARNING_CANDIDATE_INVALID", "statement obrigatório")
	}
	if validity == "" {
		return nil, contextError("LEARNING_CANDIDATE_INVALID", "validity obrigatória")
	}
	tags, err := contextLearningTextList(raw["tags"], "tags", true)
	if err != nil {
		return nil, err
	}
	conflicts, err := contextLearningTextList(raw["conflicts"], "conflicts", false)
	if err != nil {
		return nil, err
	}
	if sourceIdentity == "" {
		relative, _ := filepath.Rel(root, source)
		sourceIdentity = filepath.ToSlash(relative)
	}
	base := map[string]any{
		"schema_version": 1, "status": "pending", "classification": classification,
		"statement": statement, "tags": tags, "validity": validity, "conflicts": conflicts,
		"evidence": evidence, "source": sourceIdentity, "source_digest": sha256Bytes(sourceBytes),
	}
	baseBytes, _ := contextCanonical(base)
	candidate := cloneMap(base)
	candidate["id"] = "L" + strings.ToUpper(sha256Bytes(baseBytes)[:12])
	candidateBytes, _ := contextCanonical(candidate)
	candidate["digest"] = sha256Bytes(candidateBytes)
	return candidate, nil
}

func contextLearningTextList(value any, label string, required bool) ([]any, error) {
	values, ok := value.([]any)
	if !ok {
		if required && value == nil {
			return nil, contextError("LEARNING_EVIDENCE_REQUIRED", label+" obrigatório")
		}
		return nil, contextError("LEARNING_CANDIDATE_INVALID", label+" exige lista de textos")
	}
	result := make([]any, 0, len(values))
	seen := map[string]bool{}
	for _, raw := range values {
		text, ok := raw.(string)
		text = strings.TrimSpace(text)
		if !ok || text == "" {
			return nil, contextError("LEARNING_CANDIDATE_INVALID", label+" exige lista de textos")
		}
		if !seen[text] {
			seen[text] = true
			result = append(result, text)
		}
	}
	if required && len(result) == 0 {
		return nil, contextError("LEARNING_EVIDENCE_REQUIRED", label+" não pode ser vazio")
	}
	return result, nil
}

func contextTruthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case float64:
		return typed != 0
	case int:
		return typed != 0
	case int64:
		return typed != 0
	case []any:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	default:
		return fmt.Sprint(value) != ""
	}
}
