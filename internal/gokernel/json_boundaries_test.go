package gokernel

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSecurityRelevantJSONRejectsTrailingGarbage(t *testing.T) {
	t.Run("actual delta", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "actual-delta.json")
		if err := os.WriteFile(path, []byte(`{"contracts":{}} trailing-garbage`), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := readActualDelta(path); err == nil {
			t.Fatal("actual delta aceitou JSON seguido de lixo")
		}
	})

	t.Run("semantic report", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "semantic.json")
		if err := os.WriteFile(path, []byte(`{"findings":[]} trailing-garbage`), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := coherenceSemanticReport(path, ""); err == nil {
			t.Fatal("relatório semântico aceitou JSON seguido de lixo")
		}
	})

	t.Run("wave frontmatter", func(t *testing.T) {
		root := t.TempDir()
		path := filepath.Join(root, "plan.md")
		content := []byte("---\n{\"id\":\"P01\"} trailing-garbage\n---\n# Plano\n")
		if err := os.WriteFile(path, content, 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := waveFrontmatter(root, path, "plano"); err == nil {
			t.Fatal("frontmatter de onda aceitou JSON seguido de lixo")
		}
	})
}
