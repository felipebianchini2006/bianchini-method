package gokernel

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"golang.org/x/text/unicode/norm"
)

var directValueFlags = map[string]bool{
	"--repo": true, "--slug": true, "--objective": true, "--scope": true,
	"--acceptance": true, "--verification": true, "--checkpoint": true,
	"--changed-file": true, "--command": true, "--blocker": true,
	"--next-action": true, "--status": true, "--behavior": true,
	"--limitation": true, "--evidence": true, "--scope-score": true,
	"--external-effect-score": true, "--migration-score": true,
	"--concurrency-score": true, "--money-score": true, "--guard": true,
	"--docviva-kind": true, "--docviva-outcome": true,
	"--docviva-artifact": true, "--docviva-justification": true,
}

var directBooleanFlags = map[string]bool{
	"--webhook-flow": true, "--payment-flow": true,
	"--production-authorized": true, "--multiple-objectives": true,
	"--destructive-migration": true, "--uncontrolled-concurrency": true,
	"--undefined-ownership": true, "--ambiguous-financial-rule": true,
	"--new-material-architecture": true,
}

func runDirect(args []string) (any, error) {
	if len(args) == 0 {
		return nil, argparseError("the following arguments are required: action")
	}
	action := args[0]
	if action == "reopen" {
		if _, err := parseFlags(args[1:], directValueFlags, directBooleanFlags); err != nil {
			return nil, err
		}
		return nil, domainError("ORDER_VIOLATION", "quick 0.4 terminal é imutável")
	}
	if action != "classify" {
		for _, allowed := range []string{"start", "status", "checkpoint", "finish"} {
			if action == allowed {
				return nil, domainError("NOT_IMPLEMENTED", "direct "+action+" não está disponível no backend go-preview")
			}
		}
		return nil, argparseError(fmt.Sprintf("argument action: invalid choice: '%s'", action))
	}
	flags, err := parseFlags(args[1:], directValueFlags, directBooleanFlags)
	if err != nil {
		return nil, err
	}
	return classifyDirect(flags)
}

type riskSignal struct {
	floor  int
	reason string
	kind   string
}

func classifyDirect(flags parsedFlags) (map[string]any, error) {
	dimensionNames := []struct {
		flag string
		name string
	}{
		{"--scope-score", "scope"},
		{"--external-effect-score", "external_effect"},
		{"--migration-score", "migration"},
		{"--concurrency-score", "concurrency"},
		{"--money-score", "money"},
	}
	dimensions := make(map[string]int, len(dimensionNames))
	declaredScore := 0
	for _, item := range dimensionNames {
		value, err := scoreValue(flags, item.flag)
		if err != nil {
			return nil, err
		}
		dimensions[item.name] = value
		declaredScore += value
	}

	overrideFlags := []struct {
		flag string
		name string
	}{
		{"--multiple-objectives", "multiple_objectives"},
		{"--destructive-migration", "destructive_migration"},
		{"--uncontrolled-concurrency", "uncontrolled_concurrency"},
		{"--undefined-ownership", "undefined_ownership"},
		{"--ambiguous-financial-rule", "ambiguous_financial_rule"},
		{"--new-material-architecture", "new_material_architecture"},
	}
	explicitOverrides := make([]string, 0)
	for _, item := range overrideFlags {
		if flags.booleans[item.flag] {
			explicitOverrides = append(explicitOverrides, item.name)
		}
	}
	overrides := append([]string(nil), explicitOverrides...)
	if dimensions["scope"] == 2 {
		overrides = append(overrides, "multiple_objectives")
	}
	if dimensions["migration"] == 2 {
		overrides = append(overrides, "destructive_migration")
	}
	if dimensions["concurrency"] == 2 {
		overrides = append(overrides, "uncontrolled_concurrency")
	}
	overrides = uniqueSorted(overrides)

	signals := make([]riskSignal, 0)
	dimensionTotal := 0
	for _, item := range dimensionNames {
		value := dimensions[item.name]
		dimensionTotal += value
		if value == 0 {
			continue
		}
		floor := value
		if value == 2 {
			switch item.name {
			case "scope", "external_effect":
				floor = 3
			default:
				floor = 5
			}
		}
		signals = append(signals, riskSignal{floor: floor, reason: fmt.Sprintf("flag:%s=%d", item.name, value), kind: item.name})
	}
	if dimensionTotal > 0 {
		signals = append(signals, riskSignal{floor: minInt(10, dimensionTotal), reason: fmt.Sprintf("flags:dimension_total=%d", dimensionTotal)})
	}

	booleanPolicies := map[string]struct {
		floor int
		kind  string
	}{
		"payment": {3, "payment"}, "webhook": {3, "webhook"},
		"multiple_objectives":       {3, "multiple_objectives"},
		"destructive_migration":     {5, "migration"},
		"uncontrolled_concurrency":  {5, "concurrency"},
		"undefined_ownership":       {3, "ownership"},
		"ambiguous_financial_rule":  {4, "money"},
		"new_material_architecture": {4, "architecture"},
	}
	structuredFlags := map[string]any{
		"concurrency": dimensions["concurrency"], "external_effect": dimensions["external_effect"],
		"migration": dimensions["migration"], "money": dimensions["money"],
		"payment": flags.booleans["--payment-flow"], "scope": dimensions["scope"],
		"webhook": flags.booleans["--webhook-flow"],
	}
	for _, name := range []string{"payment", "webhook"} {
		if structuredFlags[name].(bool) {
			policy := booleanPolicies[name]
			signals = append(signals, riskSignal{floor: policy.floor, reason: "flag:" + name + "=true", kind: policy.kind})
		}
	}
	for _, name := range explicitOverrides {
		policy := booleanPolicies[name]
		signals = append(signals, riskSignal{floor: policy.floor, reason: "flag:" + name + "=true", kind: policy.kind})
		structuredFlags[name] = true
	}
	for _, path := range flags.values["--changed-file"] {
		relative, pathSignals, err := riskPathSignals(path)
		if err != nil {
			return nil, err
		}
		_ = relative
		signals = append(signals, pathSignals...)
	}

	initialFloor := 0
	reasons := make([]string, 0)
	guards := make([]string, 0)
	for _, signal := range signals {
		initialFloor = maxInt(initialFloor, signal.floor)
		reasons = append(reasons, signal.reason)
		guards = append(guards, guardsFor(signal.kind)...)
	}
	if declaredScore < initialFloor {
		reasons = append(reasons, fmt.Sprintf("declared_below_floor:%d<%d", declaredScore, initialFloor))
	}
	for _, item := range dimensionNames {
		if value := dimensions[item.name]; value > 0 {
			reasons = append(reasons, fmt.Sprintf("%s=%d", item.name, value))
		}
	}
	for _, override := range overrides {
		reasons = append(reasons, "override:"+override)
	}
	reasons = uniqueSorted(reasons)
	guards = uniqueSorted(guards)
	changedPaths := uniqueSorted(flags.values["--changed-file"])
	effectiveScore := maxInt(declaredScore, initialFloor)
	return map[string]any{
		"additional_guards": guards,
		"declared_score":    declaredScore,
		"derived_floor":     initialFloor,
		"diff_floor":        0,
		"dimensions":        dimensions,
		"effective_score":   effectiveScore,
		"initial_floor":     initialFloor,
		"overrides":         overrides,
		"phase":             "start",
		"reasons":           reasons,
		"reclassified":      false,
		"risk_contract":     "quick-risk-floor-v1",
		"risk_inputs":       map[string]any{"declared_paths": changedPaths, "flags": structuredFlags},
		"route":             map[bool]string{true: "protected", false: "normal"}[effectiveScore >= 3],
		"schema_version":    1,
		"score":             effectiveScore,
		"workflow":          "quick",
	}, nil
}

func riskPathSignals(path string) (string, []riskSignal, error) {
	if err := validateRiskPath(path); err != nil {
		return "", nil, err
	}
	clean := filepath.ToSlash(filepath.Clean(path))
	parts := strings.Split(strings.ToLower(clean), "/")
	directories := parts[:len(parts)-1]
	basename := parts[len(parts)-1]
	ignoredDomain := len(parts) > 0 && containsAny(
		[]string{parts[0]}, "doc", "docs", "note", "notes", "test", "tests",
		"example", "examples", "fixtures",
	)
	signals := make([]riskSignal, 0)
	if containsAny(directories, "migration", "migrations", "migrate") {
		signals = append(signals, riskSignal{3, "declared_path:migration:" + clean, "migration"})
	}
	if !ignoredDomain && containsAny(directories, "payment", "payments", "billing", "ledger", "money", "financial") {
		signals = append(signals, riskSignal{3, "declared_path:payment:" + clean, "payment"})
	}
	if !ignoredDomain && containsAny(directories, "webhook", "webhooks") {
		signals = append(signals, riskSignal{3, "declared_path:webhook:" + clean, "webhook"})
	}
	if containsAny(
		[]string{basename},
		"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
		"pyproject.toml", "poetry.lock", "requirements.txt", "pom.xml",
		"build.gradle", "build.gradle.kts", "go.mod", "go.sum", "cargo.toml",
		"cargo.lock", "gemfile", "gemfile.lock", "composer.json", "composer.lock",
	) {
		signals = append(signals, riskSignal{3, "declared_path:dependency_manifest:" + clean, "dependency_manifest"})
	}
	if containsAny(directories, "contract", "contracts", "schema", "schemas") ||
		containsAny([]string{filepath.Ext(basename)}, ".proto", ".graphql", ".gql", ".avsc") ||
		containsAny(
			[]string{basename}, "openapi.json", "openapi.yaml", "openapi.yml",
			"swagger.json", "swagger.yaml", "swagger.yml",
		) {
		signals = append(signals, riskSignal{3, "declared_path:contract:" + clean, "contract"})
	}
	return clean, signals, nil
}

func validateRiskPath(path string) error {
	if path == "" {
		return riskInputError("declared_paths vazio")
	}
	if strings.Contains(path, "\\") {
		return riskInputError("declared_paths contém barra invertida: " + path)
	}
	if filepath.IsAbs(path) || filepath.ToSlash(filepath.Clean(path)) != path {
		return riskInputError("declared_paths deve ser POSIX relativo: " + path)
	}
	for _, part := range strings.Split(path, "/") {
		if part == "" || part == "." || part == ".." {
			return riskInputError("declared_paths contém traversal: " + path)
		}
		if strings.EqualFold(part, ".planning") {
			return riskInputError("declared_paths usa namespace estrangeiro")
		}
	}
	if !norm.NFC.IsNormalString(path) {
		return riskInputError("declared_paths não está em NFC: " + path)
	}
	return nil
}

func guardsFor(kind string) []string {
	return map[string][]string{
		"external_effect":     {"official_docs", "rollback", "sandbox", "timeout_recovery"},
		"migration":           {"backup_restore", "migration_verify", "rollback"},
		"concurrency":         {"deduplication", "idempotency", "replay_order"},
		"money":               {"idempotency", "persistence", "reconciliation", "sandbox", "source_of_truth"},
		"payment":             {"idempotency", "persistence", "reconciliation", "source_of_truth", "timeout_recovery"},
		"webhook":             {"authenticity", "deduplication", "persistence", "replay_order"},
		"multiple_objectives": {"local_contract"},
		"ownership":           {"local_contract", "owner_approval"},
		"architecture":        {"architecture_review", "local_contract"},
		"dependency_manifest": {"dependency_audit", "lockfile_consistency"},
		"contract":            {"contract_tests", "local_contract"},
	}[kind]
}

func containsAny(values []string, targets ...string) bool {
	for _, value := range values {
		for _, target := range targets {
			if value == target {
				return true
			}
		}
	}
	return false
}

func uniqueSorted(values []string) []string {
	set := make(map[string]struct{}, len(values))
	for _, value := range values {
		set[value] = struct{}{}
	}
	result := make([]string, 0, len(set))
	for value := range set {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func minInt(left, right int) int {
	if left < right {
		return left
	}
	return right
}

func maxInt(left, right int) int {
	if left > right {
		return left
	}
	return right
}
