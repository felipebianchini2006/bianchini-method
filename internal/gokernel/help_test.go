package gokernel

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStaticCLIHelpCoversCanonicalCommandPaths(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("..", "..", "contracts", "cli-surfaces.json"))
	if err != nil {
		t.Fatal(err)
	}
	var contract struct {
		Commands map[string]json.RawMessage `json:"commands"`
		Surfaces []struct {
			Command string `json:"command"`
			Action  string `json:"action"`
		} `json:"surfaces"`
	}
	if err := json.Unmarshal(content, &contract); err != nil {
		t.Fatal(err)
	}

	assertHelp := func(args ...string) {
		t.Helper()
		text, ok := staticCLIHelp(args)
		if !ok || text == "" || text[len(text)-1] != '\n' {
			t.Fatalf("missing canonical static help for %q", args)
		}
	}
	assertHelp("--help")
	for command := range contract.Commands {
		assertHelp(command, "--help")
	}
	for _, surface := range contract.Surfaces {
		if surface.Action != "" {
			assertHelp(surface.Command, surface.Action, "--help")
		}
	}
}

func TestStaticCLIHelpRejectsAbsentConsumedOrUnknownHelp(t *testing.T) {
	for _, args := range [][]string{{}, {"direct"}, {"direct", "classify"}, {"--version"}, {"direct", "classify", "--scope", "--help"}, {"unknown", "--help"}} {
		if _, ok := staticCLIHelp(args); ok {
			t.Fatalf("unexpectedly handled non-help argv %q", args)
		}
	}
}

func TestRunMatchesOracleHelpAtEveryAcceptedPosition(t *testing.T) {
	tests := []struct {
		args []string
		path string
	}{
		{args: []string{"direct", "--repo", ".", "--help"}, path: "direct"},
		{args: []string{"direct", "--help", "classify"}, path: "direct"},
		{args: []string{"direct", "classify", "--help", "extra"}, path: "direct"},
		{args: []string{"--help", "version"}, path: ""},
	}
	for _, test := range tests {
		var stdout, stderr bytes.Buffer
		if code := Run(test.args, &stdout, &stderr); code != 0 || stderr.Len() != 0 || stdout.String() != staticCLIHelpByPath[test.path] {
			t.Fatalf("Run(%q) exit=%d stdout=%q stderr=%q", test.args, code, stdout.String(), stderr.String())
		}
	}
}

func TestRunServesEveryEmbeddedHelpPathExactly(t *testing.T) {
	for path, want := range staticCLIHelpByPath {
		args := append(strings.Fields(path), "--help")
		var stdout bytes.Buffer
		var stderr bytes.Buffer
		if code := Run(args, &stdout, &stderr); code != 0 {
			t.Fatalf("Run(%q) exit=%d stderr=%q", args, code, stderr.String())
		}
		if stderr.Len() != 0 || stdout.String() != want {
			t.Fatalf("Run(%q) diverged from embedded oracle help", args)
		}
	}
}
