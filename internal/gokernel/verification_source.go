package gokernel

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
)

func verificationSourceFingerprint(root string) (string, error) {
	command := exec.Command("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
	command.Dir = root
	output, err := command.Output()
	if err != nil {
		return "", workflowError("DIRTY_WORKSPACE", "não foi possível inventariar o código")
	}
	paths := []string{}
	for _, raw := range bytes.Split(output, []byte{0}) {
		relative := filepath.ToSlash(string(raw))
		if relative == "" || relative == ".bianchini" || strings.HasPrefix(relative, ".bianchini/") {
			continue
		}
		if err := validateRiskPath(relative); err != nil {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código escapou do repo")
		}
		paths = append(paths, relative)
	}
	sort.Strings(paths)
	digest := sha256.New()
	for _, relative := range paths {
		path := filepath.Join(root, filepath.FromSlash(relative))
		info, statErr := os.Lstat(path)
		if os.IsNotExist(statErr) {
			_, _ = digest.Write([]byte(relative + "\x00deleted\x00"))
			continue
		}
		if statErr != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código não é regular: "+relative)
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return "", workflowError("STALE_EVIDENCE", "arquivo do código ilegível: "+relative)
		}
		_, _ = digest.Write([]byte(relative + "\x00" + info.Mode().Perm().String() + "\x00"))
		fileDigest := sha256.Sum256(content)
		_, _ = digest.Write(fileDigest[:])
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}
