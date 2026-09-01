package gokernel

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

func extractUpdateArchive(content []byte, destination string) (string, error) {
	compressed, err := gzip.NewReader(bytes.NewReader(content))
	if err != nil {
		return "", userError("archive de atualização inválido: " + err.Error())
	}
	defer compressed.Close()
	reader := tar.NewReader(compressed)
	seen := map[string]bool{}
	total := int64(0)
	members := 0
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", userError("archive de atualização inválido: " + err.Error())
		}
		members++
		name, err := safeUpdateArchivePath(header.Name)
		if err != nil {
			return "", err
		}
		if seen[name] {
			return "", userError("arquivo duplicado no pacote: " + header.Name)
		}
		seen[name] = true
		if header.Typeflag != tar.TypeDir && header.Typeflag != tar.TypeReg && header.Typeflag != tar.TypeRegA {
			return "", userError("arquivo inseguro no pacote: " + header.Name)
		}
		if header.Size < 0 || total > maxUpdateArchiveBytes-header.Size {
			return "", userError("conteúdo extraído excede o limite seguro")
		}
		total += header.Size
		target := filepath.Join(destination, filepath.FromSlash(name))
		if !pathWithin(destination, target) {
			return "", userError("arquivo inseguro no pacote: " + header.Name)
		}
		if header.Typeflag == tar.TypeDir {
			if err := os.MkdirAll(target, 0o755); err != nil {
				return "", userError("archive de atualização inválido: " + err.Error())
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return "", userError("archive de atualização inválido: " + err.Error())
		}
		file, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, os.FileMode(header.Mode)&0o777)
		if err != nil {
			return "", userError("archive de atualização inválido: " + err.Error())
		}
		written, copyErr := io.CopyN(file, reader, header.Size)
		closeErr := file.Close()
		if copyErr != nil || written != header.Size || closeErr != nil {
			return "", userError("arquivo inválido no pacote: " + header.Name)
		}
		mode := os.FileMode(header.Mode) & 0o777
		if mode == 0 {
			mode = 0o644
		}
		if err := os.Chmod(target, mode); err != nil {
			return "", userError("archive de atualização inválido: " + err.Error())
		}
	}
	if members == 0 {
		return "", userError("archive de atualização vazio")
	}
	candidates := make([]string, 0)
	err = filepath.WalkDir(destination, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return userError("arquivo inseguro no pacote: " + path)
		}
		if entry.Name() == "VERSION" && filepath.Base(filepath.Dir(path)) == "_shared" && filepath.Base(filepath.Dir(filepath.Dir(path))) == "skills" && entry.Type().IsRegular() {
			candidates = append(candidates, path)
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	if len(candidates) != 1 {
		return "", userError("archive não contém uma única raiz válida do Bianchini Method")
	}
	return filepath.Dir(filepath.Dir(candidates[0])), nil
}

func safeUpdateArchivePath(name string) (string, error) {
	if name == "" || strings.Contains(name, "\\") || strings.HasPrefix(name, "/") {
		return "", userError(fmt.Sprintf("arquivo inseguro no pacote: %q", name))
	}
	parts := strings.Split(name, "/")
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return "", userError("arquivo inseguro no pacote: " + name)
		}
	}
	return strings.Join(parts, "/"), nil
}

func validateRemoteSkills(remoteSkills, latest, installed string, lineageManifest []byte) error {
	remoteVersion, err := readInstalledUpdateVersion(remoteSkills)
	if err != nil {
		return err
	}
	if remoteVersion != latest {
		return userError("versão do archive diverge da versão consultada")
	}
	if lineageManifest != nil {
		manifestPath := filepath.Join(remoteSkills, filepath.FromSlash(lineageResetManifest))
		info, err := os.Lstat(manifestPath)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return userError("archive não contém manifesto de reset regular")
		}
		archiveManifest, err := os.ReadFile(manifestPath)
		if err != nil || !bytes.Equal(archiveManifest, lineageManifest) {
			return userError("manifesto de reset do archive diverge da fonte oficial consultada")
		}
		if err := validateLineageManifest(archiveManifest, installed, latest); err != nil {
			return err
		}
	}
	for _, name := range managedSkillDirectories {
		if err := rejectUpdateTreeLinks(filepath.Join(remoteSkills, name), "pacote "+name); err != nil {
			return err
		}
	}
	return nil
}

func rejectUpdateTreeLinks(root, label string) error {
	info, err := os.Lstat(root)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return userError(label + " deve ser diretório regular: " + root)
	}
	return filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return userError(label + ": " + walkErr.Error())
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return userError(label + " contém symlink: " + path)
		}
		if !entry.IsDir() && !entry.Type().IsRegular() {
			return userError(label + " contém entrada não regular: " + path)
		}
		return nil
	})
}

func pathWithin(root, candidate string) bool {
	relative, err := filepath.Rel(filepath.Clean(root), filepath.Clean(candidate))
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative)
}
