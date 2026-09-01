package gokernel

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func contextRoot(value string) (string, error) {
	if value == "" {
		var err error
		value, err = os.Getwd()
		if err != nil {
			return "", contextError("PACK_INCOMPLETE", "repo ausente")
		}
	}
	if strings.Contains(value, "\\") {
		return "", contextError("PATH_UNSAFE", "repo contém separador inválido")
	}
	absolute, err := filepath.Abs(value)
	if err != nil {
		return "", contextError("PACK_INCOMPLETE", "repo ausente: "+value)
	}
	info, err := os.Lstat(absolute)
	if err != nil || !info.IsDir() {
		return "", contextError("PACK_INCOMPLETE", "repo ausente: "+absolute)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", contextError("PATH_UNSAFE", "repo não pode ser symlink: "+absolute)
	}
	bianchini := filepath.Join(absolute, ".bianchini")
	info, err = os.Lstat(bianchini)
	if err == nil && info.Mode()&os.ModeSymlink != 0 {
		return "", contextError("PATH_UNSAFE", ".bianchini atravessa symlink: "+bianchini)
	}
	if err != nil || !info.IsDir() {
		return "", contextError("PACK_INCOMPLETE", ".bianchini ausente")
	}
	if err := contextRejectSymlinkChain(absolute, bianchini, ".bianchini"); err != nil {
		return "", err
	}
	return filepath.Clean(absolute), nil
}

func contextSafePath(root, value, label string) (string, error) {
	if strings.Contains(value, "\\") {
		return "", contextError("PATH_UNSAFE", label+" contém separador inválido")
	}
	if value == "" {
		return "", contextError("PATH_UNSAFE", label+" vazio")
	}
	for _, part := range strings.Split(filepath.ToSlash(value), "/") {
		if part == ".." {
			return "", contextError("PATH_UNSAFE", label+" contém traversal: "+value)
		}
	}
	candidate := value
	if !filepath.IsAbs(candidate) {
		candidate = filepath.Join(root, filepath.FromSlash(candidate))
	}
	absolute, err := filepath.Abs(candidate)
	if err != nil {
		return "", contextError("PATH_UNSAFE", label+" inválido")
	}
	absolute = filepath.Clean(absolute)
	relative, err := filepath.Rel(root, absolute)
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", contextError("PATH_UNSAFE", fmt.Sprintf("%s sai do repo: %s", label, value))
	}
	for _, part := range strings.Split(filepath.ToSlash(relative), "/") {
		if part == "" || part == "." || part == ".." {
			return "", contextError("PATH_UNSAFE", fmt.Sprintf("%s contém traversal: %s", label, value))
		}
		if strings.EqualFold(part, ".planning") {
			return "", contextError("PATH_UNSAFE", label+" usa namespace estrangeiro")
		}
	}
	if err := contextRejectSymlinkChain(root, absolute, label); err != nil {
		return "", err
	}
	return absolute, nil
}

func contextRejectSymlinkChain(root, target, label string) error {
	relative, err := filepath.Rel(root, target)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return contextError("PATH_UNSAFE", label+" sai do repo")
	}
	current := root
	if info, statErr := os.Lstat(current); statErr != nil || info.Mode()&os.ModeSymlink != 0 {
		return contextError("PATH_UNSAFE", label+" atravessa symlink")
	}
	if relative == "." {
		return nil
	}
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		info, statErr := os.Lstat(current)
		if statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return contextError("PATH_UNSAFE", label+" atravessa symlink: "+current)
		}
		if statErr != nil && !os.IsNotExist(statErr) {
			return contextError("PATH_UNSAFE", label+" inválido")
		}
	}
	return nil
}

func contextExistingFile(root, value, label string) (string, error) {
	path, err := contextSafePath(root, value, label)
	if err != nil {
		return "", err
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		relative, _ := filepath.Rel(root, path)
		return "", contextError("PACK_INCOMPLETE", label+" ausente: "+filepath.ToSlash(relative))
	}
	return path, nil
}

func contextSafeOutput(root, value string) (string, error) {
	path, err := contextSafePath(root, value, "output")
	if err != nil {
		return "", err
	}
	runtime := filepath.Join(root, ".bianchini", ".runtime", "context")
	relative, err := filepath.Rel(runtime, path)
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		if relative == "." {
			return "", contextError("PATH_UNSAFE", "output exige nome de arquivo")
		}
		return "", contextError("PATH_UNSAFE", "output deve ficar em .bianchini/.runtime/context")
	}
	if info, statErr := os.Lstat(path); statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return "", contextError("PATH_UNSAFE", "output existente não é arquivo regular")
		}
	} else if !os.IsNotExist(statErr) {
		return "", contextError("PATH_UNSAFE", "output inválido")
	}
	return path, nil
}

func contextChildren(directory, label string) ([]string, error) {
	info, err := os.Lstat(directory)
	if err == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil, contextError("PATH_UNSAFE", label+" não pode ser symlink")
	}
	if err != nil || !info.IsDir() {
		return nil, contextError("PACK_INCOMPLETE", label+" ausente")
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, contextError("PACK_INCOMPLETE", label+" ausente")
	}
	result := make([]string, 0, len(entries))
	for _, entry := range entries {
		path := filepath.Join(directory, entry.Name())
		child, statErr := os.Lstat(path)
		if statErr != nil {
			return nil, contextError("PACK_INCOMPLETE", label+" contém entrada ilegível: "+entry.Name())
		}
		if child.Mode()&os.ModeSymlink != 0 {
			return nil, contextError("PATH_UNSAFE", label+" contém symlink: "+entry.Name())
		}
		result = append(result, path)
	}
	sort.Strings(result)
	return result, nil
}

func contextPrefixedDirectory(root, directory, identifier, label string) (string, error) {
	children, err := contextChildren(directory, label)
	if err != nil {
		return "", err
	}
	matches := make([]string, 0)
	for _, candidate := range children {
		info, statErr := os.Lstat(candidate)
		name := filepath.Base(candidate)
		if statErr == nil && info.IsDir() && (name == identifier || strings.HasPrefix(name, identifier+"-")) {
			matches = append(matches, candidate)
		}
	}
	if len(matches) != 1 {
		return "", contextError("PACK_INCOMPLETE", fmt.Sprintf("%s %s exige uma correspondência; encontradas %d", label, identifier, len(matches)))
	}
	return contextSafePath(root, matches[0], label)
}

func contextDebugPath(root, identifier string) (string, error) {
	matches := make([]string, 0)
	for _, state := range []string{"active", "resolved"} {
		directory := filepath.Join(root, ".bianchini", "debug", state)
		if _, err := os.Lstat(directory); os.IsNotExist(err) {
			continue
		}
		children, err := contextChildren(directory, "debug/"+state)
		if err != nil {
			return "", err
		}
		for _, candidate := range children {
			info, statErr := os.Lstat(candidate)
			stem := strings.TrimSuffix(filepath.Base(candidate), filepath.Ext(candidate))
			if statErr == nil && info.Mode().IsRegular() && (stem == identifier || strings.HasPrefix(stem, identifier+"-")) {
				matches = append(matches, candidate)
			}
		}
		if len(matches) > 0 {
			break
		}
	}
	if len(matches) != 1 {
		return "", contextError("PACK_INCOMPLETE", fmt.Sprintf("debug %s exige uma correspondência; encontradas %d", identifier, len(matches)))
	}
	return matches[0], nil
}
