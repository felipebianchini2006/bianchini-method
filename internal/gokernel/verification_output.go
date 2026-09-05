package gokernel

import (
	"bytes"
	"os"
	"regexp"
	"strings"
)

// Drain the process without retaining unbounded output in memory.
type verificationOutput struct {
	bytes.Buffer
	truncated bool
}

func (b *verificationOutput) Write(p []byte) (int, error) {
	n := len(p)
	remaining := 256*1024 - b.Len()
	if len(p) > remaining {
		p = p[:remaining]
		b.truncated = true
	}
	_, _ = b.Buffer.Write(p)
	return n, nil
}

var sensitiveOutput = regexp.MustCompile(`(?i)((?:authorization|password|passwd|secret|token|api[_-]?key)["']?\s*[:=]\s*["']?(?:bearer\s+|basic\s+)?)[^\s,"';}]+`)
var credentialURL = regexp.MustCompile(`(?i)(https?://)[^/\s:@]+:[^/\s@]+@`)

func sanitizeVerificationOutput(value []byte) string {
	text := strings.ToValidUTF8(string(value), "?")
	for _, entry := range os.Environ() {
		parts := strings.SplitN(entry, "=", 2)
		key := strings.ToLower(parts[0])
		if len(parts) == 2 && len(parts[1]) >= 4 && (strings.Contains(key, "token") || strings.Contains(key, "secret") || strings.Contains(key, "password") || strings.Contains(key, "key")) {
			text = strings.ReplaceAll(text, parts[1], "[REDACTED]")
		}
	}
	text = sensitiveOutput.ReplaceAllString(text, "${1}[REDACTED]")
	return credentialURL.ReplaceAllString(text, "${1}[REDACTED]@")
}
