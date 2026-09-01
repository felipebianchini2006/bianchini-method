package gokernel

import (
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
