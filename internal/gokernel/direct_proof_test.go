package gokernel

import (
	"os"
	"strings"
	"testing"
)

func TestQuickRejectsUnexecutedAndFailedCommands(t *testing.T) {
	for _, command := range []string{"", "bm-command-that-does-not-exist", "go command-that-does-not-exist"} {
		t.Run(command, func(t *testing.T) {
			repo := workflowTestRepo(t, true)
			declared := command
			if declared == "" {
				declared = "go version"
			}
			started, err := runDirectLifecycle("start", []string{"--repo", repo, "--objective", "internal", "--scope", "internal", "--acceptance", "contract", "--verification", declared})
			if err != nil {
				t.Fatal(err)
			}
			id := stateString(started.(map[string]any)["id"])
			args := []string{"--repo", repo, "--slug", id, "--checkpoint", "success", "--next-action", "finish", "--evidence", "tests passed"}
			if command != "" {
				args = append(args, "--command", command)
			}
			_, err = runDirectLifecycle("checkpoint", args)
			if command != "" {
				if err == nil || !strings.Contains(err.Error(), "VERIFICATION_FAILED") {
					t.Fatalf("failed command accepted: %v", err)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			_, err = runDirectLifecycle("finish", []string{"--repo", repo, "--slug", id, "--status", "completed", "--next-action", "done", "--verification", "passed", "--docviva-kind", "internal", "--docviva-outcome", "not_applicable", "--docviva-justification", "no behavior change"})
			if err == nil {
				t.Fatal("narrative completion accepted")
			}
			if _, err := os.Stat(repo + "/.bianchini/quick/" + id + "/RESULT.md"); !os.IsNotExist(err) {
				t.Fatal("failed closure wrote result")
			}
		})
	}
}

func TestDebugRejectsNarrativeRed(t *testing.T) {
	repo := workflowTestRepo(t, true)
	started, err := runDebug([]string{"start", "--repo", repo, "--objective", "defect", "--expected", "pass", "--actual", "fail", "--environment", "local"})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(started.(map[string]any)["id"])
	for _, event := range []string{"reproduced", "diagnosed"} {
		_, err := runDebug([]string{"checkpoint", "--repo", repo, "--id", id, "--event", event, "--evidence", "observed", "--root-cause", "broken invariant"})
		if err != nil {
			t.Fatal(err)
		}
	}
	if _, err := runDebug([]string{"checkpoint", "--repo", repo, "--id", id, "--event", "red", "--evidence", "red"}); err == nil {
		t.Fatal("narrative red accepted")
	}
}

func TestQuickRejectsForeignAndStaleProofs(t *testing.T) {
	repo := workflowTestRepo(t, true)
	workspace := newMethodWorkspace(repo)
	directory := repo + "/.bianchini/quick/Q001-proof"
	brief := map[string]any{"id": "Q001-proof", "digest": strings.Repeat("a", 64), "verification": []any{"go version"}}
	ids, err := verifyQuickCommands(workspace, directory, brief, []string{"go version"}, "")
	if err != nil {
		t.Fatal(err)
	}
	events := []any{map[string]any{"proof_ids": stringSliceAny(ids)}}
	if _, err := validateQuickProofs(workspace, directory, brief, events); err != nil {
		t.Fatal(err)
	}
	if _, err := validateQuickProofs(workspace, repo+"/.bianchini/quick/Q002-other", brief, events); err == nil {
		t.Fatal("foreign quick proof accepted")
	}
	if err := os.WriteFile(repo+"/changed.txt", []byte("new behavior"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := validateQuickProofs(workspace, directory, brief, events); err == nil {
		t.Fatal("stale quick proof accepted")
	}
}
