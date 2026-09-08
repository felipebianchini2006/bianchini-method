package gokernel

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type scopePageRecord struct {
	Page   int      `json:"page"`
	Items  []string `json:"items"`
	Reason string   `json:"reason,omitempty"`
}

// Extraction records are declarations made by the extractor. Reconciling them
// establishes coverage of that record, not semantic fidelity to the PDF.
type scopeExtractionRecord struct {
	SourceSHA256 string            `json:"source_sha256"`
	PageCount    int               `json:"page_count"`
	Tool         string            `json:"tool"`
	Pages        []scopePageRecord `json:"pages"`
}

func readScopeExtractionRecord(path string) (scopeExtractionRecord, error) {
	var record scopeExtractionRecord
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() > maxScopeBytes {
		return record, scopeError("SCOPE_COVERAGE_INVALID", "manifesto de páginas ausente ou inválido")
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return record, err
	}
	// Keep the same duplicate-key protection as all other persisted contracts.
	if _, err := decodeStrictJSONObject(content); err != nil {
		return record, scopeError("SCOPE_COVERAGE_INVALID", err.Error())
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&record); err != nil {
		return record, scopeError("SCOPE_COVERAGE_INVALID", err.Error())
	}
	return record, nil
}

func reconcileScopeExtraction(record scopeExtractionRecord, body, sourceHash string, pages int) error {
	invalid := func(message string) error { return scopeError("SCOPE_COVERAGE_INVALID", message) }
	if record.SourceSHA256 != sourceHash || record.PageCount != pages || strings.TrimSpace(record.Tool) == "" {
		return invalid("manifesto deve identificar a fonte, quantidade declarada de páginas e ferramenta")
	}
	items, err := parseScopeItems(body)
	if err != nil {
		return err
	}
	references := map[string]map[int]bool{}
	for _, item := range items {
		for _, line := range strings.Split(item.block, "\n") {
			if !strings.HasPrefix(line, "- Fonte:") {
				continue
			}
			itemPages, err := scopeSourcePages(strings.TrimSpace(strings.TrimPrefix(line, "- Fonte:")), pages)
			if err != nil {
				return err
			}
			references[item.id] = map[int]bool{}
			for _, page := range itemPages {
				references[item.id][page] = true
			}
		}
	}
	seen, coverage := map[int]bool{}, map[string]map[int]bool{}
	for _, record := range record.Pages {
		if record.Page < 1 || record.Page > pages || seen[record.Page] {
			return invalid("página inválida ou repetida no manifesto")
		}
		seen[record.Page] = true
		if len(record.Items) == 0 && strings.TrimSpace(record.Reason) == "" {
			return invalid(fmt.Sprintf("página %d sem itens exige justificativa", record.Page))
		}
		if len(record.Items) > 0 && strings.TrimSpace(record.Reason) != "" {
			return invalid("justificativa de ausência não pode acompanhar itens extraídos")
		}
		for _, id := range record.Items {
			if !references[id][record.Page] {
				return invalid(fmt.Sprintf("%s não referencia página %d no escopo", id, record.Page))
			}
			if coverage[id] == nil {
				coverage[id] = map[int]bool{}
			}
			if coverage[id][record.Page] {
				return invalid("item repetido na mesma página")
			}
			coverage[id][record.Page] = true
		}
	}
	for page := 1; page <= pages; page++ {
		if !seen[page] {
			return invalid(fmt.Sprintf("página %d ausente do manifesto", page))
		}
	}
	for id, pages := range references {
		for page := range pages {
			if !coverage[id][page] {
				return invalid(fmt.Sprintf("%s da página %d ausente do manifesto", id, page))
			}
		}
	}
	return nil
}

func scopeExtractionValue(record scopeExtractionRecord) map[string]any {
	content, _ := json.Marshal(record)
	value, _ := decodeStrictJSONObject(content)
	return value
}
