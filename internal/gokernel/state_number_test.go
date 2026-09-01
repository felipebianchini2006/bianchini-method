package gokernel

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStateIntRejectsFractionalNonFiniteAndOverflowNumbers(t *testing.T) {
	for name, value := range map[string]any{
		"fractional float":  1.5,
		"fractional json":   json.Number("1.5"),
		"nan":               math.NaN(),
		"positive infinity": math.Inf(1),
		"negative infinity": math.Inf(-1),
		"overflow":          math.MaxFloat64,
	} {
		t.Run(name, func(t *testing.T) {
			if got := stateInt(value); got != 0 {
				t.Fatalf("stateInt(%v)=%d; want 0", value, got)
			}
		})
	}
}

func TestValidateStateRejectsFractionalMethodVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "PROJECT_STATE.json")
	if err := os.WriteFile(path, []byte("{\"method_version\":2.5}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	code, stdout, stderr := runCLI(t, "validate-state", path)
	if code != 2 || stdout != "" || !strings.Contains(stderr, "schema v2 não deve validar projeto legado") {
		t.Fatalf("fractional method_version accepted: code=%d stdout=%q stderr=%q", code, stdout, stderr)
	}
}
