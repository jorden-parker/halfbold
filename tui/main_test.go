package main

import (
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestDescribeScanErrorEscapesFontFileNameKeepingDirectory(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "Fonts\x1b")
	if err := os.Mkdir(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	broken := filepath.Join(dir, "Evil\x1b]2;x\x07.ttf")
	if err := os.Symlink(filepath.Join(dir, "missing.ttf"), broken); err != nil {
		t.Fatal(err)
	}
	_, err := scanFonts([]string{dir})
	if err == nil {
		t.Fatal("expected a scan error for the dangling font")
	}
	got := describeScanError(err, []string{dir})
	want := "open " + dir + `/Evil\x1b]2;x\x07.ttf: no such file or directory`
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestDescribeScanErrorKeepsScannedDirectoryErrorRaw(t *testing.T) {
	dir := "/fonts\x1b"
	err := &fs.PathError{Op: "open", Path: dir, Err: fs.ErrPermission}
	if got := describeScanError(err, []string{dir}); got != "open /fonts\x1b: permission denied" {
		t.Fatalf("got %q", got)
	}
}

func TestDescribeScanErrorKeepsPlainErrorsUnchanged(t *testing.T) {
	err := fs.ErrNotExist
	if got := describeScanError(err, nil); got != err.Error() {
		t.Fatalf("got %q, want %q", got, err.Error())
	}
}
