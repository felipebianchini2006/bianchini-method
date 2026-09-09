package gokernel

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestEvidenceIndexAndStatusSurviveArchiveWithoutRewritingProofs(t *testing.T) {
	repo, change := executionWorkspaceRepository(t, verificationPlan([]string{"go", "version"}))
	context := verificationContextPack(t, repo, change)
	result, err := runVerify([]string{"task", "--repo", repo, "--change", change, "--plan", "P01", "--task", "T01", "--context-pack", context})
	if err != nil {
		t.Fatal(err)
	}
	id := stateString(result.(map[string]any)["proof_id"])
	directory := filepath.Join(repo, ".bianchini", "changes", change)
	proofPath := filepath.Join(directory, "results", "proofs", id+".json")
	content, err := os.ReadFile(proofPath)
	if err != nil {
		t.Fatal(err)
	}
	proof, err := decodeStrictJSONObject(content)
	if err != nil {
		t.Fatal(err)
	}
	if stateString(proof["log_path"]) != "results/logs/"+id+".log" {
		t.Fatalf("log is not change-relative: %v", proof["log_path"])
	}
	// Preserve an authentic 1.1.0-shaped record to exercise historical lookup.
	proof["log_path"] = ".bianchini/changes/" + change + "/results/logs/" + id + ".log"
	proof["record_digest"] = verificationRecordDigest(proof)
	content, _ = json.Marshal(proof)
	if err := os.WriteFile(proofPath, content, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := recordVerificationReviewForTest(repo, change, id); err != nil {
		t.Fatal(err)
	}
	for _, archive := range []bool{false, true} {
		if archive {
			destination := filepath.Join(repo, ".bianchini", "archive", change)
			if err := os.Rename(directory, destination); err != nil {
				t.Fatal(err)
			}
			directory = destination
		}
		status, err := verificationStatus(repo, change)
		if err != nil {
			t.Fatal(err)
		}
		if status["archived"] != archive || len(stateArray(status["logs"])) != 1 {
			t.Fatalf("status=%v", status)
		}
		log := stateString(stateObject(stateArray(status["logs"])[0])["log_path"])
		if _, err := os.Stat(filepath.Join(repo, log)); err != nil {
			t.Fatal(err)
		}
		index := filepath.Join(directory, "plans", "P01", "evidence", "INDEX.md")
		body, err := os.ReadFile(index)
		if err != nil {
			t.Fatal(err)
		}
		links := regexp.MustCompile(`\]\(([^)]+)\)`).FindAllSubmatch(body, -1)
		if len(links) != 3 {
			t.Fatalf("expected proof, log and review links: %s", body)
		}
		for _, link := range links {
			if _, err := os.Stat(filepath.Join(filepath.Dir(index), string(link[1]))); err != nil {
				t.Fatal(err)
			}
		}
		stored, _ := os.ReadFile(filepath.Join(directory, "results", "proofs", id+".json"))
		if !bytes.Equal(stored, content) {
			t.Fatal("status rewrote sealed record")
		}
	}
	if err := os.WriteFile(filepath.Join(directory, "results", "logs", id+".log"), []byte("tampered"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := verificationStatus(repo, change); err == nil || !strings.Contains(err.Error(), "STALE_EVIDENCE") {
		t.Fatalf("tampered archived log accepted: %v", err)
	}
}

func recordVerificationReviewForTest(repo, change, proof string) (any, error) {
	return runVerify([]string{"review", "--repo", repo, "--change", change, "--scope", "task", "--plan", "P01", "--task", "T01", "--reviewer", "test", "--verdict", "approved", "--proof", proof})
}
