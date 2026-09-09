package gokernel

import (
	"bytes"
	"encoding/binary"
	"hash/crc32"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"testing"

	"github.com/felipebianchini2006/bianchini-method/internal/acceptance"
)

func TestScreenshotDimensionsAreBoundedBeforeDecode(t *testing.T) {
	for _, size := range [][2]uint32{{16385, 2}, {2, 16385}, {8192, 8192}} {
		var encoded bytes.Buffer
		if err := png.Encode(&encoded, image.NewRGBA(image.Rect(0, 0, 2, 2))); err != nil {
			t.Fatal(err)
		}
		content := encoded.Bytes()
		binary.BigEndian.PutUint32(content[16:20], size[0])
		binary.BigEndian.PutUint32(content[20:24], size[1])
		binary.BigEndian.PutUint32(content[29:33], crc32.ChecksumIEEE(content[12:29]))
		root := t.TempDir()
		if err := os.WriteFile(filepath.Join(root, "large.png"), content, 0600); err != nil {
			t.Fatal(err)
		}
		err := inspectHomologationEvidence(root, root, acceptance.Evidence{Kind: "screenshot", Path: "large.png", SHA256: sha256Bytes(content)})
		if err == nil || err.Error() != "screenshot não contém imagem válida" {
			t.Fatalf("dimensions %v were not rejected before decoding: %v", size, err)
		}
	}
}
