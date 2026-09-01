package gokernel

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

type contextGoldenFile struct {
	InitialTree map[string]struct {
		Text string `json:"text"`
		Mode string `json:"mode"`
	} `json:"initial_tree"`
	Steps []struct {
		Surface  string   `json:"surface"`
		Argv     []string `json:"argv"`
		Expected struct {
			Stdout struct {
				Value map[string]any `json:"value"`
			} `json:"stdout"`
		} `json:"expected"`
	} `json:"steps"`
}

func contextGoldenRepo(t *testing.T) (string, contextGoldenFile) {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "..", "tests", "fixtures", "cli_contract", "success-context.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture contextGoldenFile
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	repo := filepath.Join(t.TempDir(), "repo")
	if err := os.MkdirAll(repo, 0o755); err != nil {
		t.Fatal(err)
	}
	for relative, specification := range fixture.InitialTree {
		target := filepath.Join(repo, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(target, []byte(specification.Text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	contextGit(t, repo, "init", "-q", "-b", "main")
	contextGit(t, repo, "config", "user.name", "BM Fixture")
	contextGit(t, repo, "config", "user.email", "fixture@example.invalid")
	return repo, fixture
}

func contextGit(t *testing.T, repo string, args ...string) string {
	t.Helper()
	command := exec.Command("git", args...)
	command.Dir = repo
	command.Env = append(os.Environ(),
		"GIT_AUTHOR_DATE=2000-01-01T00:00:00Z",
		"GIT_COMMITTER_DATE=2000-01-01T00:00:00Z",
	)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, output)
	}
	return strings.TrimSpace(string(output))
}

func contextResultMap(t *testing.T, value any) map[string]any {
	t.Helper()
	result, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("resultado inesperado: %#v", value)
	}
	return result
}

func contextTestFrontmatter(t *testing.T, value map[string]any, title string) []byte {
	t.Helper()
	encoded, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	return []byte("---\n" + string(encoded) + "\n---\n# " + title + "\n")
}

func TestContextGoldenPackAndVerify(t *testing.T) {
	repo, fixture := contextGoldenRepo(t)
	packed, err := runContext([]string{"pack", "--repo", repo, "--unit", "C001/P01/T01"})
	if err != nil {
		t.Fatal(err)
	}
	expectedPack := fixture.Steps[0].Expected.Stdout.Value
	packedCanonical, _ := contextCanonical(packed)
	expectedPackCanonical, _ := contextCanonical(expectedPack)
	if !bytes.Equal(packedCanonical, expectedPackCanonical) {
		actual, _ := json.MarshalIndent(packed, "", "  ")
		expected, _ := json.MarshalIndent(expectedPack, "", "  ")
		payload, _ := os.ReadFile(filepath.Join(repo, ".bianchini", ".runtime", "context", "C001-P01-T01.json"))
		t.Fatalf("pack divergiu\nactual=%s\nexpected=%s\npayload=%s", actual, expected, payload)
	}
	path := filepath.Join(repo, ".bianchini", ".runtime", "context", "C001-P01-T01.json")
	verified, err := runContext([]string{"verify", "--repo", repo, "--path", path})
	if err != nil {
		t.Fatal(err)
	}
	expectedVerify := fixture.Steps[1].Expected.Stdout.Value
	verifiedCanonical, _ := contextCanonical(verified)
	expectedVerifyCanonical, _ := contextCanonical(expectedVerify)
	if !bytes.Equal(verifiedCanonical, expectedVerifyCanonical) {
		t.Fatalf("verify divergiu: %#v != %#v", verified, expectedVerify)
	}

	payloadRaw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(payloadRaw, &payload); err != nil {
		t.Fatal(err)
	}
	context := stateObject(payload["context"])
	encoded, _ := json.Marshal(context)
	for _, forbidden := range []string{"IRRELEVANT_RESULT_MUST_NOT_LOAD", "IRRELEVANT_TASK_RESULT", "CONTEUDO_IRRELEVANTE_SPEC", "ARCHIVE_MUST_NOT_LOAD"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("conteúdo irrelevante carregado: %s", forbidden)
		}
	}
	if got := stateObject(context["plan"])["schema_version"]; !contextExactInt(got, 2) {
		t.Fatalf("schema 2 do plano não preservado: %#v", got)
	}
	if got := payload["schema_version"]; !contextExactInt(got, 1) {
		t.Fatalf("schema 1 do pack não preservado: %#v", got)
	}
}

func TestContextLimitAndStaleFailClosed(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	output := filepath.Join(repo, ".bianchini", ".runtime", "context", "small.json")
	_, err := runContext([]string{"pack", "--repo", repo, "--unit", "C001/P01/T01", "--output", output, "--max-bytes", "256"})
	if err == nil || !strings.Contains(err.Error(), "PACK_TOO_LARGE") || !strings.Contains(err.Error(), "largest_consumers") {
		t.Fatalf("erro de limite inesperado: %v", err)
	}
	if _, statErr := os.Lstat(output); !os.IsNotExist(statErr) {
		t.Fatalf("pack limitado não deveria existir: %v", statErr)
	}

	result, err := runContext([]string{"pack", "--repo", repo, "--unit", "C001/P01/T01"})
	if err != nil {
		t.Fatal(err)
	}
	pack := filepath.Join(repo, filepath.FromSlash(stateString(contextResultMap(t, result)["path"])))
	scope := filepath.Join(repo, ".bianchini", "changes", "C001-context", "SCOPE.md")
	file, err := os.OpenFile(scope, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = file.WriteString("\nDrift.\n")
	_ = file.Close()
	_, err = runContext([]string{"verify", "--repo", repo, "--path", pack})
	if err == nil || !strings.Contains(err.Error(), "STALE_EVIDENCE") {
		t.Fatalf("drift deveria invalidar pack: %v", err)
	}
}

func TestContextPathSafetyRejectsForeignNamespaceAndSymlinks(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	outside := filepath.Join(t.TempDir(), "outside.json")
	_, err := runContext([]string{"pack", "--repo", repo, "--unit", "C001/P01", "--output", outside})
	if err == nil || !strings.Contains(err.Error(), "PATH_UNSAFE") {
		t.Fatalf("output externo deveria falhar: %v", err)
	}
	_, err = runContext([]string{"verify", "--repo", repo, "--path", filepath.Join(repo, ".PLANNING", "pack.json")})
	if err == nil || !strings.Contains(err.Error(), "PATH_UNSAFE") {
		t.Fatalf("namespace estrangeiro deveria falhar: %v", err)
	}

	realRuntime := filepath.Join(repo, ".bianchini", "runtime-real")
	if err := os.MkdirAll(realRuntime, 0o755); err != nil {
		t.Fatal(err)
	}
	runtimeLink := filepath.Join(repo, ".bianchini", ".runtime")
	if err := os.Symlink(realRuntime, runtimeLink); err != nil {
		t.Fatal(err)
	}
	_, err = runContext([]string{"pack", "--repo", repo, "--unit", "C001/P01"})
	if err == nil || !strings.Contains(err.Error(), "PATH_UNSAFE") {
		t.Fatalf("symlink de output deveria falhar: %v", err)
	}
}

func TestContextPlanQuickDebugAndReleaseCandidate(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	for _, unit := range []string{"C001/P01", "Q012", "D004"} {
		packed, err := compileContextPack(repo, unit, "", contextDefaultMaxBytes)
		if err != nil {
			t.Fatalf("pack %s: %v", unit, err)
		}
		path := filepath.Join(repo, filepath.FromSlash(stateString(packed["path"])))
		verified, err := verifyContextPack(repo, path)
		if err != nil {
			t.Fatalf("verify %s: %v", unit, err)
		}
		if stateString(verified["unit"]) != unit {
			t.Fatalf("unidade divergente: %#v", verified)
		}
	}
	if _, err := compileContextPack(repo, "RC:build-a", "", contextDefaultMaxBytes); err == nil || !strings.Contains(err.Error(), "PACK_INCOMPLETE") {
		t.Fatalf("RC sem homologação deveria falhar: %v", err)
	}
	homologation := filepath.Join(repo, ".bianchini", "changes", "C001-context", "results", "HOMOLOGATION.md")
	value := map[string]any{
		"schema_version": 1, "fingerprint": "build-a", "change": "C001-context", "status": "running",
		"gates": []any{"release-tests"}, "blockers": []any{},
		"findings":      []any{map[string]any{"id": "visual-review", "status": "open"}},
		"required_refs": []any{".bianchini/changes/C001-context/results/P00.md"},
	}
	if err := os.WriteFile(homologation, contextTestFrontmatter(t, value, "Homologação"), 0o644); err != nil {
		t.Fatal(err)
	}
	packed, err := compileContextPack(repo, "RC:build-a", "", contextDefaultMaxBytes)
	if err != nil {
		t.Fatal(err)
	}
	payloadRaw, _ := os.ReadFile(filepath.Join(repo, filepath.FromSlash(stateString(packed["path"]))))
	var payload map[string]any
	if err := json.Unmarshal(payloadRaw, &payload); err != nil {
		t.Fatal(err)
	}
	if got := stateString(stateObject(stateObject(payload["context"])["release_candidate"])["fingerprint"]); got != "build-a" {
		t.Fatalf("RC divergente: %s", got)
	}
	if !contextContainsString(stateArray(payload["required_refs"]), "release-candidate:build-a") {
		t.Fatalf("referência de RC ausente: %#v", payload["required_refs"])
	}

	change := filepath.Join(repo, ".bianchini", "changes", "C001-context")
	archive := filepath.Join(repo, ".bianchini", "archive", "C001-context")
	if err := os.Rename(change, archive); err != nil {
		t.Fatal(err)
	}
	archived, err := compileContextPack(repo, "RC:build-a", "", contextDefaultMaxBytes)
	if err != nil {
		t.Fatal(err)
	}
	archivedRaw, _ := os.ReadFile(filepath.Join(repo, filepath.FromSlash(stateString(archived["path"]))))
	var archivedPayload map[string]any
	_ = json.Unmarshal(archivedRaw, &archivedPayload)
	if got := stateString(stateObject(archivedPayload["context"])["source"]); got != ".bianchini/archive/C001-context/results/HOMOLOGATION.md" {
		t.Fatalf("fonte arquivada divergente: %s", got)
	}
}

func TestContextCacheHeadAndCanonicalTampering(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	first, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes)
	if err != nil {
		t.Fatal(err)
	}
	second, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes)
	if err != nil {
		t.Fatal(err)
	}
	if first["cache_hit"] != false || second["cache_hit"] != true || first["digest"] != second["digest"] {
		t.Fatalf("cache divergente: %#v / %#v", first, second)
	}
	pack := filepath.Join(repo, filepath.FromSlash(stateString(first["path"])))
	if info, err := os.Stat(pack); err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("modo atômico divergente: %v / %v", info, err)
	}
	raw, _ := os.ReadFile(pack)
	var payload map[string]any
	_ = json.Unmarshal(raw, &payload)
	stateObject(stateObject(payload["context"])["task"])["result"] = "resultado adulterado"
	forged, _ := contextCanonical(payload)
	if err := os.WriteFile(pack, forged, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyContextPack(repo, pack); err == nil || !strings.Contains(err.Error(), "STALE_EVIDENCE") {
		t.Fatalf("conteúdo adulterado deveria falhar: %v", err)
	}

	if err := os.WriteFile(pack, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	contextGit(t, repo, "add", ".bianchini/STATE.md")
	contextGit(t, repo, "commit", "-q", "-m", "estabelece head")
	if _, err := verifyContextPack(repo, pack); err == nil || !strings.Contains(err.Error(), "HEAD mudou") {
		t.Fatalf("mudança de HEAD deveria invalidar pack: %v", err)
	}
}

func TestContextIncludesOnlyGovernedRelevantLessons(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	directory := filepath.Join(repo, ".bianchini", "changes", "C001-context", "results", "learning")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, candidate := range map[string]map[string]any{
		"relevant": {
			"classification": "repeatable_procedure", "statement": "Usar escrita durável.",
			"tags": []any{"session-state"}, "validity": "Enquanto o contrato session-state existir.", "conflicts": []any{},
		},
		"irrelevant": {
			"classification": "repeatable_procedure", "statement": "Não deve entrar.",
			"tags": []any{"src/other.py"}, "validity": "Enquanto o outro módulo existir.", "conflicts": []any{},
		},
	} {
		value := map[string]any{
			"status": "completed", "green": "teste passou", "evidence": []any{"teste determinístico passou"},
			"learning_candidate": candidate,
		}
		if err := os.WriteFile(filepath.Join(directory, name+".md"), contextTestFrontmatter(t, value, name), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	proposed, err := learningPropose(repo, "")
	if err != nil {
		t.Fatal(err)
	}
	relevantID := ""
	for _, raw := range stateArray(proposed["candidates"]) {
		item := stateObject(raw)
		path := filepath.Join(repo, filepath.FromSlash(stateString(item["path"])))
		candidateRaw, _ := os.ReadFile(path)
		var candidate map[string]any
		_ = json.Unmarshal(candidateRaw, &candidate)
		if stateString(candidate["statement"]) == "Usar escrita durável." {
			relevantID = stateString(item["id"])
		}
		if _, err := learningApprove(repo, stateString(item["id"]), stateString(item["digest"]), "human:test"); err != nil {
			t.Fatal(err)
		}
	}
	if relevantID == "" {
		t.Fatal("candidato relevante não encontrado")
	}
	packed, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(filepath.Join(repo, filepath.FromSlash(stateString(packed["path"]))))
	var payload map[string]any
	_ = json.Unmarshal(raw, &payload)
	lessons := stateArray(stateObject(payload["context"])["approved_lessons"])
	if len(lessons) != 1 || stateString(stateObject(lessons[0])["id"]) != relevantID {
		t.Fatalf("seleção de lições divergente: %#v", lessons)
	}

	source := filepath.Join(directory, "relevant.md")
	archived := filepath.Join(repo, ".bianchini", "archive", "C001-context", "results", "learning", "relevant.md")
	if err := os.MkdirAll(filepath.Dir(archived), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(source, archived); err != nil {
		t.Fatal(err)
	}
	if _, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes); err != nil {
		t.Fatalf("fonte histórica arquivada deveria ser válida: %v", err)
	}
}

func TestContextRejectsForgedLessonAndSourceSymlink(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	lessons := filepath.Join(repo, ".bianchini", "current", "lessons")
	if err := os.MkdirAll(lessons, 0o755); err != nil {
		t.Fatal(err)
	}
	forged := map[string]any{
		"id": "LAAAAAAAAAAAA", "schema_version": 1, "status": "approved", "active": true,
		"classification": "repeatable_procedure", "statement": "Não confiar.", "tags": []any{"session-state"},
		"validity": "Sempre.", "conflicts": []any{}, "evidence": []any{"nenhuma"},
		"source": ".bianchini/changes/C001-context/results/P00.md", "source_digest": strings.Repeat("0", 64),
		"approved_by": "human:forged", "approved_digest": strings.Repeat("0", 64), "approved_at": "2026-09-01T00:00:00Z",
	}
	encoded, _ := contextCanonical(forged)
	if err := os.WriteFile(filepath.Join(lessons, "LAAAAAAAAAAAA.json"), encoded, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes); err == nil || !strings.Contains(err.Error(), "PACK_INCOMPLETE") {
		t.Fatalf("lição forjada deveria falhar: %v", err)
	}
	if err := os.RemoveAll(lessons); err != nil {
		t.Fatal(err)
	}

	scope := filepath.Join(repo, ".bianchini", "changes", "C001-context", "SCOPE.md")
	real := filepath.Join(repo, ".bianchini", "changes", "C001-context", "SCOPE.real.md")
	if err := os.Rename(scope, real); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(real, scope); err != nil {
		t.Fatal(err)
	}
	if _, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes); err == nil || !strings.Contains(err.Error(), "PATH_UNSAFE") {
		t.Fatalf("fonte symlink deveria falhar: %v", err)
	}
}

func TestContextCLIRequiredArguments(t *testing.T) {
	if _, err := runContext([]string{"pack"}); err == nil || err.Error() != "context pack exige --unit" {
		t.Fatalf("erro de pack divergente: %v", err)
	}
	if _, err := runContext([]string{"verify"}); err == nil || err.Error() != "context verify exige --path" {
		t.Fatalf("erro de verify divergente: %v", err)
	}
}

func TestContextRejectsSpecTraversalAndCasefoldForeignNamespace(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	manifestPath := filepath.Join(repo, ".bianchini", "changes", "C001-context", "specs", "MANIFEST.json")
	raw, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	var manifest map[string]any
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	spec := stateObject(stateArray(manifest["specs"])[0])
	for _, malicious := range []string{"../../../STATE.md", ".PLANNING/secret.md"} {
		spec["path"] = malicious
		encoded, _ := json.MarshalIndent(manifest, "", "  ")
		if err := os.WriteFile(manifestPath, append(encoded, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
		if _, err := compileContextPack(repo, "C001/P01/T01", "", contextDefaultMaxBytes); err == nil || !strings.Contains(err.Error(), "PATH_UNSAFE") {
			t.Fatalf("spec target %q deveria falhar: %v", malicious, err)
		}
	}
}

func TestContextCandidateAcceptsBooleanGreenFromOracleContract(t *testing.T) {
	repo, _ := contextGoldenRepo(t)
	source := filepath.Join(repo, ".bianchini", "changes", "C001-context", "results", "boolean-green.md")
	value := map[string]any{
		"status": "completed", "green": true, "evidence": []any{"teste aprovado"},
		"learning_candidate": map[string]any{
			"classification": "repeatable_procedure", "statement": "Preservar o contrato.",
			"tags": []any{"session-state"}, "validity": "Enquanto o contrato existir.", "conflicts": []any{},
		},
	}
	content := contextTestFrontmatter(t, value, "Boolean green")
	if err := os.WriteFile(source, content, 0o644); err != nil {
		t.Fatal(err)
	}
	candidate, err := contextCandidateFromSource(repo, source, ".bianchini/changes/C001-context/results/boolean-green.md", content)
	if err != nil {
		t.Fatal(err)
	}
	if candidate == nil || !learningIDPattern.MatchString(stateString(candidate["id"])) || !contextDigestPattern.MatchString(stateString(candidate["digest"])) {
		t.Fatalf("candidato governado inválido: %#v", candidate)
	}
}
