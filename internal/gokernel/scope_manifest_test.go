package gokernel

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func completeScopeRecord() scopeExtractionRecord {
	return scopeExtractionRecord{SourceSHA256: "source", PageCount: 2, Tool: "pdf extractor", Pages: []scopePageRecord{
		{Page: 1, Items: []string{"ACT-001", "FLW-001", "REQ-001"}},
		{Page: 2, Items: []string{}, Reason: "Página final sem requisitos"},
	}}
}

func TestScopeExtractionReconcilesEveryDeclaredPageAndItem(t *testing.T) {
	if err := reconcileScopeExtraction(completeScopeRecord(), scopeDraft(false), "source", 2); err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name   string
		mutate func(*scopeExtractionRecord)
	}{
		{"missing page", func(r *scopeExtractionRecord) { r.Pages = r.Pages[:1] }},
		{"missing item", func(r *scopeExtractionRecord) { r.Pages[0].Items = []string{"ACT-001", "FLW-001"} }},
		{"unknown item", func(r *scopeExtractionRecord) { r.Pages[0].Items = append(r.Pages[0].Items, "REQ-099") }},
		{"duplicate page", func(r *scopeExtractionRecord) { r.Pages[1].Page = 1 }},
		{"unexplained page", func(r *scopeExtractionRecord) { r.Pages[1].Reason = "" }},
		{"wrong source", func(r *scopeExtractionRecord) { r.SourceSHA256 = "other" }},
		{"wrong count", func(r *scopeExtractionRecord) { r.PageCount = 3 }},
		{"misattributed item", func(r *scopeExtractionRecord) { r.Pages[1].Items = []string{"REQ-001"}; r.Pages[1].Reason = "" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			record := completeScopeRecord()
			test.mutate(&record)
			if err := reconcileScopeExtraction(record, scopeDraft(false), "source", 2); err == nil {
				t.Fatal("incomplete extraction accepted")
			}
		})
	}
}

func TestScopeSealDoesNotClaimSemanticVerification(t *testing.T) {
	body, coverage, err := validateScopeBody(scopeDraft(false), 2)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(body, "Páginas processadas:") || !strings.Contains(body, "Páginas declaradas pelo extrator: 2") || coverage["semantic_fidelity"] != "not_verified_by_cli" || coverage["page_processing"] != "declared" {
		t.Fatalf("scope overstates its evidence: %v\n%s", coverage, body)
	}
}

func TestScopePageManifestRejectsAmbiguousJSON(t *testing.T) {
	path := filepath.Join(t.TempDir(), "pages.json")
	if err := os.WriteFile(path, []byte(`{"page_count":2,"page_count":1}`), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := readScopeExtractionRecord(path); err == nil {
		t.Fatal("duplicate keys accepted")
	}
}
