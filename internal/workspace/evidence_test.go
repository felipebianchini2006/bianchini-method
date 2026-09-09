package workspace

import (
	"path/filepath"
	"testing"
)

func TestResolveLogKeepsChangeIdentity(t *testing.T) {
	change := filepath.Join(t.TempDir(), ".bianchini", "archive", "C001-test")
	for _, ref := range []string{"results/logs/proof.log", ".bianchini/changes/C001-test/results/logs/proof.log", ".bianchini/archive/C001-test/results/logs/proof.log"} {
		got, err := ResolveLog(change, ref)
		if err != nil || got != filepath.Join(change, "results", "logs", "proof.log") {
			t.Fatalf("%s: %s %v", ref, got, err)
		}
	}
	for _, ref := range []string{"", "../proof.log", "results/logs/../../proof.log", "results/logs/sub/proof.log", ".bianchini/changes/C002-other/results/logs/proof.log", "/results/logs/proof.log", "C:/results/logs/proof.log", `results/logs/..\proof.log`} {
		if _, err := ResolveLog(change, ref); err == nil {
			t.Fatalf("unsafe reference accepted: %s", ref)
		}
	}
}
