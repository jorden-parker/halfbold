package main

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
	"sort"
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

func os2Bytes(serifStyle, proportion byte) []byte {
	data := make([]byte, 42)
	data[32] = 2
	data[33] = serifStyle
	data[35] = proportion
	return data
}

func postBytes(fixedPitch uint32) []byte {
	data := make([]byte, 16)
	binary.BigEndian.PutUint32(data[12:16], fixedPitch)
	return data
}

func buildSfntWithTables(t *testing.T, tables map[string][]byte) []byte {
	t.Helper()
	tags := make([]string, 0, len(tables))
	for tag := range tables {
		tags = append(tags, tag)
	}
	sort.Strings(tags)
	data := make([]byte, 12+16*len(tags))
	binary.BigEndian.PutUint32(data[0:4], 0x00010000)
	binary.BigEndian.PutUint16(data[4:6], uint16(len(tags)))
	for i, tag := range tags {
		rec := 12 + i*16
		copy(data[rec:rec+4], tag)
		binary.BigEndian.PutUint32(data[rec+8:rec+12], uint32(len(data)))
		binary.BigEndian.PutUint32(data[rec+12:rec+16], uint32(len(tables[tag])))
		data = append(data, tables[tag]...)
	}
	return data
}

func TestFontKindMonoFromPost(t *testing.T) {
	data := buildSfntWithTables(t, map[string][]byte{
		"post": postBytes(1),
		"OS/2": os2Bytes(0, 3),
	})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := fontKind(data, dir, "Plain"); got != "mono" {
		t.Fatalf("got %q, want mono", got)
	}
}

func TestFontKindMonoFromPanoseProportion(t *testing.T) {
	data := buildSfntWithTables(t, map[string][]byte{
		"OS/2": os2Bytes(0, 9),
	})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := fontKind(data, dir, "Plain"); got != "mono" {
		t.Fatalf("got %q, want mono", got)
	}
}

func TestFontKindSerifFromPanose(t *testing.T) {
	data := buildSfntWithTables(t, map[string][]byte{
		"OS/2": os2Bytes(4, 3),
	})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := fontKind(data, dir, "Plain"); got != "serif" {
		t.Fatalf("got %q, want serif", got)
	}
}

func TestFontKindSansFromPanose(t *testing.T) {
	data := buildSfntWithTables(t, map[string][]byte{
		"OS/2": os2Bytes(11, 3),
	})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got := fontKind(data, dir, "Something Serif"); got != "sans" {
		t.Fatalf("got %q, want sans", got)
	}
}

func TestFontKindFallsBackToName(t *testing.T) {
	data := buildSfntWithTables(t, map[string][]byte{})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	cases := map[string]string{
		"Fancy Serif":             "serif",
		"Fancy Sans Serif":        "sans",
		"JetBrainsMono Nerd Font": "mono",
		"Source Code Pro":         "mono",
		"Pair":                    "sans",
	}
	for family, want := range cases {
		if got := fontKind(data, dir, family); got != want {
			t.Fatalf("fontKind(%q) = %q, want %q", family, got, want)
		}
	}
}

func TestReadTableDirectoryOffsets(t *testing.T) {
	post := postBytes(1)
	data := buildSfntWithTables(t, map[string][]byte{"post": post})
	dir, err := readTableDirectory(data)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	r, ok := dir["post"]
	if !ok {
		t.Fatal("expected post table in directory")
	}
	if int(r.offset) != 12+16 {
		t.Fatalf("got offset %d, want %d", r.offset, 12+16)
	}
	got := tableBytes(data, dir, "post")
	if !bytes.Equal(got, post) {
		t.Fatalf("got %v, want %v", got, post)
	}
}

func TestGroupCandidatesCarriesKind(t *testing.T) {
	files := []fontFile{
		{path: "/f/Mono-Regular.ttf", family: "Mono", subfamily: "Regular", kind: "mono"},
		{path: "/f/Mono-Bold.ttf", family: "Mono", subfamily: "Bold", kind: "mono"},
		{path: "/f/Serif.ttf", family: "Serif", subfamily: "Regular", variable: true, kind: "serif"},
	}
	candidates := groupCandidates(files)
	byLabel := map[string]candidate{}
	for _, c := range candidates {
		byLabel[c.label] = c
	}
	if byLabel["Mono"].kind != "mono" {
		t.Fatalf("expected mono kind, got %+v", byLabel["Mono"])
	}
	if byLabel["Serif"].kind != "serif" {
		t.Fatalf("expected serif kind, got %+v", byLabel["Serif"])
	}
}

func TestFamilyNameStripsVariableSuffix(t *testing.T) {
	got := familyName(candidate{label: "Inter (variable)"})
	if got != "Inter" {
		t.Fatalf("got %q, want Inter", got)
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
