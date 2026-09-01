package gokernel

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

const maxUpdateReleaseMetadataBytes = 64 * 1024

var updateReleaseDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)
var updateReleaseCommit = regexp.MustCompile(`^[0-9a-f]{7,64}$`)

type updateReleaseArtifact struct {
	Target  string `json:"target"`
	Archive string `json:"archive"`
	SHA256  string `json:"sha256"`
	Size    int64  `json:"size"`
	Binary  string `json:"binary"`
}

type updateReleaseManifest struct {
	SchemaVersion int                     `json:"schema_version"`
	Version       string                  `json:"version"`
	BuildCommit   string                  `json:"build_commit"`
	SourceEpoch   int64                   `json:"source_date_epoch"`
	Artifacts     []updateReleaseArtifact `json:"artifacts"`
}

func updateReleaseAssetURL(version, asset string) (string, error) {
	if _, err := parseUpdateVersion(version); err != nil {
		return "", err
	}
	if asset == "" || filepath.Base(asset) != asset || strings.ContainsAny(asset, `/\\`) {
		return "", userError("asset de release inválido")
	}
	return "https://github.com/" + officialUpdateRepository + "/releases/download/v" + version + "/" + asset, nil
}

func updateArchiveIdentity(version, goos, goarch string) (string, string, string, error) {
	url, err := updateArchiveURL(version, goos, goarch)
	if err != nil {
		return "", "", "", err
	}
	target := goos + "-" + goarch
	name := "bianchini-method_" + version + "_" + target + ".tar.gz"
	binary := "skills/_shared/bin/bm"
	if goos == "windows" {
		binary += ".exe"
	}
	return url, name, binary, nil
}

func validateUpdateReleaseManifest(content []byte, version, target, archive, binary string) (updateReleaseArtifact, error) {
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	var manifest updateReleaseManifest
	if err := decoder.Decode(&manifest); err != nil {
		return updateReleaseArtifact{}, userError("manifesto da release inválido: " + err.Error())
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return updateReleaseArtifact{}, userError("manifesto da release possui dados extras")
	}
	if manifest.SchemaVersion != 1 || manifest.Version != version || manifest.SourceEpoch < 0 || !updateReleaseCommit.MatchString(manifest.BuildCommit) {
		return updateReleaseArtifact{}, userError("manifesto da release diverge da versão consultada")
	}
	seen := map[string]bool{}
	var selected *updateReleaseArtifact
	for index := range manifest.Artifacts {
		artifact := &manifest.Artifacts[index]
		if artifact.Target == "" || seen[artifact.Target] || filepath.Base(artifact.Archive) != artifact.Archive ||
			!updateReleaseDigest.MatchString(artifact.SHA256) || artifact.Size <= 0 || artifact.Size > maxUpdateArchiveBytes {
			return updateReleaseArtifact{}, userError("manifesto da release contém artefato inválido")
		}
		seen[artifact.Target] = true
		if artifact.Target == target {
			selected = artifact
		}
	}
	if selected == nil || selected.Archive != archive || selected.Binary != binary {
		return updateReleaseArtifact{}, userError("manifesto da release não contém o pacote esperado para " + target)
	}
	return *selected, nil
}

func validateUpdateChecksums(content []byte, artifact updateReleaseArtifact) error {
	seen := map[string]string{}
	for lineNumber, line := range strings.Split(strings.TrimSpace(string(content)), "\n") {
		fields := strings.Fields(line)
		if len(fields) != 2 || !updateReleaseDigest.MatchString(fields[0]) || filepath.Base(fields[1]) != fields[1] {
			return userError("SHA256SUMS inválido na linha " + strconv.Itoa(lineNumber+1))
		}
		if _, duplicate := seen[fields[1]]; duplicate {
			return userError("SHA256SUMS contém arquivo duplicado: " + fields[1])
		}
		seen[fields[1]] = fields[0]
	}
	digest, ok := seen[artifact.Archive]
	if !ok || digest != artifact.SHA256 {
		return userError("SHA256SUMS diverge do manifesto da release")
	}
	return nil
}

func verifyUpdateArchive(content []byte, artifact updateReleaseArtifact) error {
	if int64(len(content)) != artifact.Size {
		return userError("tamanho do archive diverge do manifesto da release")
	}
	digestBytes := sha256.Sum256(content)
	digest := hex.EncodeToString(digestBytes[:])
	if digest != artifact.SHA256 {
		return userError("checksum do archive diverge do manifesto da release")
	}
	return nil
}
