package gokernel

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRunDesignAuditSealVerifyAndRejectSymlink(t *testing.T) {
	root := t.TempDir()
	scope := filepath.Join(root, "scope.md")
	design := filepath.Join(root, "design")
	if err := os.MkdirAll(design, 0o755); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(scope, []byte("# Scope\n"), 0o644)
	files := []string{"design/contract.md", "design/prototype.html", "design/tokens.css", "design/screen.png"}
	for _, relative := range files {
		_ = os.WriteFile(filepath.Join(root, relative), []byte("fixture\n"), 0o644)
	}
	manifestPath := filepath.Join(design, "manifest.json")
	manifest := map[string]any{
		"schema_version": 1, "status": "draft", "source": "imported",
		"scope_source": nil, "scope_digest": nil, "design_digest": nil,
		"contract": files[0], "prototype": files[1], "tokens": files[2],
		"screenshots": []string{files[3]}, "surfaces": []string{"checkout"},
		"breakpoints": []string{"mobile"}, "files": files,
	}
	raw, _ := json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)

	sealed, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("seal design: %v", err)
	}
	sealedResult := sealed.(map[string]any)
	if len(sealedResult["design_digest"].(string)) != 64 {
		t.Fatalf("invalid design digest: %v", sealedResult["design_digest"])
	}
	raw, _ = os.ReadFile(manifestPath)
	_ = json.Unmarshal(raw, &manifest)
	manifest["status"] = "approved"
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	verified, err := runDesignAudit([]string{"verify", "--root", root, "--scope", scope, "--manifest", manifestPath})
	if err != nil {
		t.Fatalf("verify design: %v", err)
	}
	if verified.(map[string]any)["design_digest"] != sealedResult["design_digest"] {
		t.Fatal("design digest changed after approval")
	}

	outside := filepath.Join(t.TempDir(), "outside.md")
	_ = os.WriteFile(outside, []byte("outside"), 0o644)
	link := filepath.Join(design, "escape.md")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	manifest["files"] = append(files, "design/escape.md")
	raw, _ = json.Marshal(manifest)
	_ = os.WriteFile(manifestPath, raw, 0o644)
	if _, err := runDesignAudit([]string{"seal", "--root", root, "--scope", scope, "--manifest", manifestPath}); err == nil {
		t.Fatal("expected symlink escape to fail")
	}
}
