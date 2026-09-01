package gokernel

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const learningFixtureSource = `---
{
  "evidence": [
    "tests/test_checkout.py::test_retry_idempotent"
  ],
  "green": "teste de contrato aprovado",
  "id": "D001-retry",
  "learning_candidate": {
    "classification": "repeatable_procedure",
    "conflicts": [],
    "statement": "Usar chave de idempotência estável no retry do checkout.",
    "tags": [
      "payments",
      "checkout",
      "src/payments.py"
    ],
    "validity": "enquanto o contrato checkout-v1 estiver ativo"
  },
  "root_cause": "retry sem chave estável",
  "schema_version": 1,
  "status": "resolved"
}
---
# Debug resolvido
`

func learningTestRepo(t *testing.T) string {
	t.Helper()
	repo := workflowTestRepo(t, true)
	source := filepath.Join(repo, ".bianchini", "debug", "resolved", "D001-retry.md")
	if err := os.WriteFile(source, []byte(learningFixtureSource), 0o644); err != nil {
		t.Fatal(err)
	}
	return repo
}

func TestGovernedLearningApproveAndDeactivate(t *testing.T) {
	repo := learningTestRepo(t)
	proposedValue, err := runLearning([]string{"propose", "--repo", repo})
	if err != nil {
		t.Fatal(err)
	}
	proposed := proposedValue.(map[string]any)
	candidates := stateArray(proposed["candidates"])
	if len(candidates) != 1 || stateInt(proposed["created"]) != 1 {
		t.Fatalf("proposed=%#v", proposed)
	}
	candidate := stateObject(candidates[0])
	id, digest := stateString(candidate["id"]), stateString(candidate["digest"])
	if id != "L813BC8BD6BAB" || digest != "99e6c101ba68154119cf7d11f6d6402d82974c669acdd408aa75c1e2ee215c35" {
		t.Fatalf("candidate=%#v", candidate)
	}
	listedValue, err := runLearning([]string{"list", "--repo", repo})
	if err != nil || len(stateArray(listedValue.(map[string]any)["pending"])) != 1 {
		t.Fatalf("listed=%#v err=%v", listedValue, err)
	}
	if _, err := runLearning([]string{"approve", "--repo", repo, "--candidate", id, "--digest", digest, "--approved-by", "agent:auto"}); err == nil || !strings.Contains(err.Error(), "HUMAN_APPROVAL_REQUIRED") {
		t.Fatalf("approval gate err=%v", err)
	}
	approvedValue, err := runLearning([]string{"approve", "--repo", repo, "--candidate", id, "--digest", digest, "--approved-by", "human:fixture"})
	if err != nil {
		t.Fatal(err)
	}
	if stateString(approvedValue.(map[string]any)["status"]) != "approved" {
		t.Fatalf("approved=%#v", approvedValue)
	}
	deactivatedValue, err := runLearning([]string{"deactivate", "--repo", repo, "--candidate", id, "--reason", "contrato substituído", "--approved-by", "human:fixture"})
	if err != nil {
		t.Fatal(err)
	}
	if deactivatedValue.(map[string]any)["active"] != false {
		t.Fatalf("deactivated=%#v", deactivatedValue)
	}
	lesson := filepath.Join(repo, ".bianchini", "current", "lessons", id+".json")
	beforeRetry, err := os.ReadFile(lesson)
	if err != nil {
		t.Fatal(err)
	}
	retriedValue, err := runLearning([]string{"deactivate", "--repo", repo, "--candidate", id, "--reason", "contrato substituído", "--approved-by", "human:fixture"})
	if err != nil {
		t.Fatalf("retry idempotente falhou: %v", err)
	}
	if retriedValue.(map[string]any)["active"] != false {
		t.Fatalf("retried=%#v", retriedValue)
	}
	afterRetry, err := os.ReadFile(lesson)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(beforeRetry, afterRetry) {
		t.Fatal("retry reescreveu a lição e alterou deactivated_at")
	}
}

func TestGovernedLearningTransitionRequiresExclusiveLock(t *testing.T) {
	repo := learningTestRepo(t)
	proposed, err := runLearning([]string{"propose", "--repo", repo})
	if err != nil {
		t.Fatal(err)
	}
	candidate := stateObject(stateArray(proposed.(map[string]any)["candidates"])[0])
	lockDirectory := filepath.Join(repo, ".bianchini", ".runtime", "learning")
	if err := os.MkdirAll(lockDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	lock, err := os.OpenFile(filepath.Join(lockDirectory, "transition.lock"), os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	defer lock.Close()
	if err := lockCloseFile(lock); err != nil {
		t.Fatal(err)
	}
	defer unlockCloseFile(lock)
	_, err = runLearning([]string{
		"approve", "--repo", repo,
		"--candidate", stateString(candidate["id"]),
		"--digest", stateString(candidate["digest"]),
		"--approved-by", "human:fixture",
	})
	if err == nil || !strings.Contains(err.Error(), "LEARNING_BUSY") {
		t.Fatalf("transição concorrente não foi bloqueada: %v", err)
	}
}

func TestGovernedLearningRejectsCandidatePathBeforeFilesystemAccess(t *testing.T) {
	repo := learningTestRepo(t)
	for _, id := range []string{"../../outside", "/absolute", `L123\\outside`, "l813bc8bd6bab"} {
		for _, args := range [][]string{
			{"approve", "--repo", repo, "--candidate", id, "--digest", strings.Repeat("0", 64), "--approved-by", "human:fixture"},
			{"reject", "--repo", repo, "--candidate", id, "--reason", "inválido"},
		} {
			if _, err := runLearning(args); err == nil || !strings.Contains(err.Error(), "LEARNING_CANDIDATE_INVALID") {
				t.Fatalf("id=%q args=%v err=%v", id, args, err)
			}
		}
	}
}

func TestGovernedLearningAcceptsTruthfulBooleanGreenOnly(t *testing.T) {
	tests := []struct {
		name      string
		green     string
		wantError bool
	}{
		{name: "true", green: "true"},
		{name: "false", green: "false", wantError: true},
		{name: "zero", green: "0", wantError: true},
		{name: "empty", green: `""`, wantError: true},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repo := learningTestRepo(t)
			source := filepath.Join(repo, ".bianchini", "debug", "resolved", "D001-retry.md")
			content := strings.Replace(learningFixtureSource, `"green": "teste de contrato aprovado"`, `"green": `+test.green, 1)
			if err := os.WriteFile(source, []byte(content), 0o644); err != nil {
				t.Fatal(err)
			}
			proposed, err := runLearning([]string{"propose", "--repo", repo})
			if test.wantError {
				if err == nil || !strings.Contains(err.Error(), "LEARNING_EVIDENCE_REQUIRED") {
					t.Fatalf("green=%s deveria ser recusado: proposed=%#v err=%v", test.green, proposed, err)
				}
				return
			}
			if err != nil || stateInt(proposed.(map[string]any)["created"]) != 1 {
				t.Fatalf("green=true deveria ser aceito: proposed=%#v err=%v", proposed, err)
			}
		})
	}
}

func TestGovernedLearningRetriesCanonicalPartialTransitions(t *testing.T) {
	for _, action := range []string{"approve", "reject"} {
		t.Run(action, func(t *testing.T) {
			repo := learningTestRepo(t)
			proposed, err := runLearning([]string{"propose", "--repo", repo})
			if err != nil {
				t.Fatal(err)
			}
			candidate := stateObject(stateArray(proposed.(map[string]any)["candidates"])[0])
			id, digest := stateString(candidate["id"]), stateString(candidate["digest"])
			originalRemove := learningRemoveFile
			calls := 0
			learningRemoveFile = func(path string) error {
				calls++
				if calls == 1 {
					if err := os.Remove(path); err != nil {
						return err
					}
					return errors.New("falha simulada no fsync após unlink")
				}
				return originalRemove(path)
			}
			defer func() { learningRemoveFile = originalRemove }()

			args := []string{action, "--repo", repo, "--candidate", id}
			target := filepath.Join(repo, ".bianchini", ".runtime", "learning", "rejected", id+".json")
			if action == "approve" {
				args = append(args, "--digest", digest, "--approved-by", "human:fixture")
				target = filepath.Join(repo, ".bianchini", "current", "lessons", id+".json")
			} else {
				args = append(args, "--reason", "caso não generalizável")
			}
			if _, err := runLearning(args); err == nil || !strings.Contains(err.Error(), "falha simulada") {
				t.Fatalf("primeira transição deveria falhar após target: %v", err)
			}
			pending := filepath.Join(repo, ".bianchini", ".runtime", "learning", "pending", id+".json")
			if !regularFile(target) {
				t.Fatalf("target canônico não foi preservado: target=%v", regularFile(target))
			}
			if _, err := os.Lstat(pending); !os.IsNotExist(err) {
				t.Fatalf("pending deveria ter sido removido antes da falha de fsync: %v", err)
			}
			if _, err := runLearning(args); err != nil {
				t.Fatalf("retry não concluiu transição parcial: %v", err)
			}
			if !regularFile(target) {
				t.Fatal("histórico final ausente após retry")
			}
			if _, err := os.Lstat(pending); !os.IsNotExist(err) {
				t.Fatalf("pending residual após retry: %v", err)
			}
		})
	}
}

func TestGovernedLearningRetriesDeactivateAfterDurableReplace(t *testing.T) {
	repo := learningTestRepo(t)
	proposed, err := runLearning([]string{"propose", "--repo", repo})
	if err != nil {
		t.Fatal(err)
	}
	candidate := stateObject(stateArray(proposed.(map[string]any)["candidates"])[0])
	id, digest := stateString(candidate["id"]), stateString(candidate["digest"])
	if _, err := runLearning([]string{"approve", "--repo", repo, "--candidate", id, "--digest", digest, "--approved-by", "human:fixture"}); err != nil {
		t.Fatal(err)
	}
	originalWrite := learningWriteFile
	calls := 0
	learningWriteFile = func(repo, path string, content []byte) error {
		calls++
		if err := originalWrite(repo, path, content); err != nil {
			return err
		}
		if calls == 1 {
			return errors.New("falha simulada após replace durável")
		}
		return nil
	}
	defer func() { learningWriteFile = originalWrite }()
	args := []string{"deactivate", "--repo", repo, "--candidate", id, "--reason", "contrato substituído", "--approved-by", "human:fixture"}
	if _, err := runLearning(args); err == nil || !strings.Contains(err.Error(), "falha simulada") {
		t.Fatalf("primeira desativação deveria reportar falha pós-replace: %v", err)
	}
	if _, err := runLearning(args); err != nil {
		t.Fatalf("retry não reconheceu desativação persistida: %v", err)
	}
	if calls != 1 {
		t.Fatalf("retry reescreveu lição já desativada: writes=%d", calls)
	}
}

func TestGovernedLearningRejectsAndDetectsTampering(t *testing.T) {
	t.Run("reject", func(t *testing.T) {
		repo := learningTestRepo(t)
		proposed, err := runLearning([]string{"propose", "--repo", repo})
		if err != nil {
			t.Fatal(err)
		}
		id := stateString(stateObject(stateArray(proposed.(map[string]any)["candidates"])[0])["id"])
		rejected, err := runLearning([]string{"reject", "--repo", repo, "--candidate", id, "--reason", "caso isolado"})
		if err != nil || stateString(rejected.(map[string]any)["status"]) != "rejected" {
			t.Fatalf("rejected=%#v err=%v", rejected, err)
		}
	})
	t.Run("tampered candidate", func(t *testing.T) {
		repo := learningTestRepo(t)
		proposed, err := runLearning([]string{"propose", "--repo", repo})
		if err != nil {
			t.Fatal(err)
		}
		candidate := stateObject(stateArray(proposed.(map[string]any)["candidates"])[0])
		path := filepath.Join(repo, filepath.FromSlash(stateString(candidate["path"])))
		if err := os.WriteFile(path, []byte("{}\n"), 0o644); err != nil {
			t.Fatal(err)
		}
		_, err = runLearning([]string{"approve", "--repo", repo, "--candidate", stateString(candidate["id"]), "--digest", stateString(candidate["digest"]), "--approved-by", "human:fixture"})
		if err == nil || !strings.Contains(err.Error(), "STALE_EVIDENCE") {
			t.Fatalf("err=%v", err)
		}
	})
}

func TestLearningRejectsSymlinkedGovernedSource(t *testing.T) {
	repo := workflowTestRepo(t, true)
	target := filepath.Join(repo, "outside.md")
	if err := os.WriteFile(target, []byte(learningFixtureSource), 0o644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(repo, ".bianchini", "debug", "resolved", "D001-retry.md")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	_, err := runLearning([]string{"propose", "--repo", repo})
	if err == nil || !strings.Contains(err.Error(), "LEARNING_PATH_INVALID") {
		t.Fatalf("err=%v", err)
	}
}
