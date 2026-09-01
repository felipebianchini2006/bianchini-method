package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestManagedManifestRejectsFractionalContractNumbersAndDuplicateKeys(t *testing.T) {
	tests := []struct {
		name    string
		content string
		want    string
	}{
		{
			name:    "fractional schema",
			content: `{"schema_version":1.5,"spec_contract":1,"specs":[],"risk_coverage":[]}`,
			want:    "schema_version deve ser 1",
		},
		{
			name:    "fractional contract",
			content: `{"schema_version":1,"spec_contract":1.9,"specs":[],"risk_coverage":[]}`,
			want:    "spec_contract deve ser 1",
		},
		{
			name:    "nested duplicate key",
			content: `{"schema_version":1,"spec_contract":1,"specs":[{"id":"auth","path":"auth.md","path":"other.md","requirements":[]}],"risk_coverage":[]}`,
			want:    "chave JSON duplicada: path",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			path := filepath.Join(root, "change", "specs", "MANIFEST.json")
			if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, []byte(test.content+"\n"), 0o644); err != nil {
				t.Fatal(err)
			}
			_, err := loadManagedManifest(root, path)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("err=%v; want %q", err, test.want)
			}
		})
	}
}
