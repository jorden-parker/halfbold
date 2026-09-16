package main

import (
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

func TestGroupCandidatesPairsRegularWithBold(t *testing.T) {
	files := []fontFile{
		{path: "/f/Mono-Regular.ttf", family: "Mono", subfamily: "Regular"},
		{path: "/f/Mono-Bold.ttf", family: "Mono", subfamily: "Bold"},
		{path: "/f/Mono-ExtraBold.ttf", family: "Mono", subfamily: "ExtraBold"},
	}
	candidates := groupCandidates(files)
	if len(candidates) != 1 {
		t.Fatalf("expected 1 candidate, got %d", len(candidates))
	}
	if candidates[0].regular != "/f/Mono-Regular.ttf" || candidates[0].bold != "/f/Mono-Bold.ttf" {
		t.Fatalf("unexpected candidate %+v", candidates[0])
	}
}

func TestGroupCandidatesSkipsFamilyWithoutBold(t *testing.T) {
	files := []fontFile{
		{path: "/f/Solo-Regular.ttf", family: "Solo", subfamily: "Regular"},
	}
	candidates := groupCandidates(files)
	if len(candidates) != 0 {
		t.Fatalf("expected 0 candidates, got %d", len(candidates))
	}
}

func TestGroupCandidatesSkipsItalics(t *testing.T) {
	files := []fontFile{
		{path: "/f/Sans-Italic.ttf", family: "Sans", subfamily: "Italic", variable: true},
		{path: "/f/Sans.ttf", family: "Sans", subfamily: "Regular", variable: true},
	}
	candidates := groupCandidates(files)
	if len(candidates) != 1 {
		t.Fatalf("expected 1 candidate, got %d", len(candidates))
	}
	if candidates[0].bold != "" {
		t.Fatalf("expected empty bold, got %q", candidates[0].bold)
	}
}

func TestGroupCandidatesStripsVariableFromLabel(t *testing.T) {
	files := []fontFile{
		{path: "/f/InterVariable.ttf", family: "Inter Variable", subfamily: "Regular", variable: true},
	}
	candidates := groupCandidates(files)
	if len(candidates) != 1 {
		t.Fatalf("expected 1 candidate, got %d", len(candidates))
	}
	if candidates[0].label != "Inter" {
		t.Fatalf("expected label Inter, got %q", candidates[0].label)
	}
}

func TestOutputPathRemovesSpaces(t *testing.T) {
	c := candidate{label: "JetBrainsMono Nerd Font"}
	got := outputPath(c, "/x")
	want := "/x/JetBrainsMonoNerdFont-Half.ttf"
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestReadTableTagsDetectsGlyfAndFvar(t *testing.T) {
	data := buildSfntHeader(t, "\x00\x01\x00\x00", [][4]byte{{'g', 'l', 'y', 'f'}, {'f', 'v', 'a', 'r'}})
	tags, err := readTableTags(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !tags["glyf"] || !tags["fvar"] {
		t.Fatalf("expected glyf and fvar tags, got %v", tags)
	}
}

func TestReadTableTagsOttoHasNoGlyf(t *testing.T) {
	data := buildSfntHeader(t, "OTTO", [][4]byte{{'C', 'F', 'F', ' '}})
	tags, err := readTableTags(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if tags["glyf"] {
		t.Fatalf("did not expect glyf tag, got %v", tags)
	}
}

func TestReadTableTagsRejectsCollections(t *testing.T) {
	data := []byte("ttcf" + "\x00\x00\x00\x00\x00\x00\x00\x00")
	if _, err := readTableTags(data); err == nil {
		t.Fatal("expected error for ttcf header")
	}
}

func TestScanFontsSkipsHalfOutputAndMissingDir(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "Foo-Half.ttf"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "notes.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	files, err := scanFonts([]string{dir, filepath.Join(dir, "missing")})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(files) != 0 {
		t.Fatalf("expected 0 files, got %d", len(files))
	}
}

func TestReadFontsSkipsMissingAndNonTrueType(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "Inter-Bold.otf")
	data := buildSfntHeader(t, "OTTO", [][4]byte{{'C', 'F', 'F', ' '}})
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
	files, err := readFonts([]string{path, filepath.Join(dir, "missing.ttf")})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(files) != 0 {
		t.Fatalf("expected 0 files, got %d", len(files))
	}
}

func buildSfntHeader(t *testing.T, version string, tags [][4]byte) []byte {
	t.Helper()
	numTables := len(tags)
	data := make([]byte, 12+16*numTables)
	copy(data[0:4], []byte(version))
	binary.BigEndian.PutUint16(data[4:6], uint16(numTables))
	for i, tag := range tags {
		offset := 12 + i*16
		copy(data[offset:offset+4], tag[:])
	}
	return data
}
