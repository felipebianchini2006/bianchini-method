package gokernel

import (
	"strings"
	"testing"
)

func TestActionParserSkipsFlagValuesBeforeSelectingAction(t *testing.T) {
	code, stdout, stderr := runCLI(t, "direct", "--scope", "classify", "foo")
	want := "bm direct: error: " + argparseInvalidChoice("action", "foo", actionCommandSpecs["direct"].actions) + "\n"
	if code != 2 || stdout != "" || !strings.HasSuffix(stderr, want) {
		t.Fatalf("flag value was treated as action: code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}

	code, _, stderr = runCLI(t, "direct", "--repo", ".", "classify")
	if code != 0 || stderr != "" {
		t.Fatalf("option before action rejected: code=%d stderr=%q", code, stderr)
	}
}

func TestActionParserRecognizesEqualsAndAbbreviationBeforeMissingAction(t *testing.T) {
	usage := strings.SplitN(staticCLIHelpByPath["direct"], "\n\n", 2)[0] + "\n"
	want := usage + "bm direct: error: the following arguments are required: action\n"
	for _, args := range [][]string{{"direct", "--scope-sc", "1"}, {"direct", "--scope-score=1"}} {
		code, stdout, stderr := runCLI(t, args...)
		if code != 2 || stdout != "" || stderr != want {
			t.Fatalf("Run(%q) diverged: code=%d stdout=%q stderr=%q", args, code, stdout, stderr)
		}
	}
}

func TestEndOfOptionsMatchesPublicCLIContract(t *testing.T) {
	plainCode, plainStdout, plainStderr := runCLI(t, "direct", "classify")
	code, stdout, stderr := runCLI(t, "direct", "--", "classify")
	if code != plainCode || stdout != plainStdout || stderr != plainStderr {
		t.Fatalf("direct separator diverged: code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}

	code, stdout, stderr = runCLI(t, "status", "--", "missingfile")
	if code != 2 || stdout != "" || stderr != "estado não encontrado: missingfile\n" {
		t.Fatalf("status separator diverged: code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}

	code, stdout, stderr = runCLI(t, "change-policy", "--")
	if code != 2 || stdout != "" || !strings.HasSuffix(stderr, "bm: error: unrecognized arguments: --\n") {
		t.Fatalf("flag-only separator diverged: code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}
