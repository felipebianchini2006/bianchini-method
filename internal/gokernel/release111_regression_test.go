package gokernel

import (
	"bytes"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/felipebianchini2006/bianchini-method/internal/acceptance"
)

func TestRelease111Regressions(t *testing.T) {
	t.Run("planning rejects invalid acceptance", func(t *testing.T) {
		for _, kind := range []string{"empty", "visual", "platform", "requirement", "duplicate"} {
			t.Run(kind, func(t *testing.T) {
				plan := roadmapPlan("P01", nil)
				scenario := stateObject(stateArray(plan["scenarios"])[0])
				switch kind {
				case "empty":
					plan["scenarios"] = []any{}
				case "visual":
					scenario["platform"] = "web"
				case "platform":
					scenario["platform"] = "unknown"
				case "requirement":
					scenario["requirements"] = []any{"REQ-999"}
				case "duplicate":
					plan["scenarios"] = []any{scenario, cloneMap(scenario)}
				}
				if err := validatePlan("P01", plan); err == nil {
					t.Fatal("regression111: invalid acceptance accepted during planning")
				}
			})
		}
	})
	t.Run("truncated screenshot", func(t *testing.T) {
		root := t.TempDir()
		var b bytes.Buffer
		if err := png.Encode(&b, image.NewRGBA(image.Rect(0, 0, 32, 32))); err != nil {
			t.Fatal(err)
		}
		content := b.Bytes()[:33]
		if _, _, err := image.DecodeConfig(bytes.NewReader(content)); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(root, "screen.png"), content, 0600); err != nil {
			t.Fatal(err)
		}
		if err := inspectHomologationEvidence(root, root, acceptance.Evidence{Kind: "screenshot", Path: "screen.png", SHA256: sha256Bytes(content)}); err == nil {
			t.Fatal("regression111: truncated screenshot accepted")
		}
	})
	t.Run("legacy plans are diagnosed", func(t *testing.T) {
		root := t.TempDir()
		if err := os.WriteFile(filepath.Join(root, "P01-old.md"), []byte("old plan"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := planFiles(root); err == nil || !strings.Contains(err.Error(), "WORKSPACE_UPGRADE_REQUIRED") {
			t.Fatalf("regression111: legacy plan silently ignored: %v", err)
		}
	})
}
