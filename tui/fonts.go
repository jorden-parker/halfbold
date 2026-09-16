package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"golang.org/x/image/font/sfnt"
)

type fontFile struct {
	path      string
	family    string
	subfamily string
	variable  bool
	kind      string
}

type candidate struct {
	label   string
	regular string
	bold    string
	kind    string
}

func scanFonts(dirs []string) ([]fontFile, error) {
	var files []fontFile
	for _, dir := range dirs {
		entries, err := os.ReadDir(dir)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, err
		}
		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			name := entry.Name()
			ext := strings.ToLower(filepath.Ext(name))
			if ext != ".ttf" && ext != ".otf" {
				continue
			}
			if strings.HasSuffix(name, "-Half.ttf") {
				continue
			}
			path := filepath.Join(dir, name)
			font, ok, err := readFont(path)
			if err != nil {
				return nil, err
			}
			if !ok {
				continue
			}
			files = append(files, font)
		}
	}
	return files, nil
}

func readFonts(paths []string) ([]fontFile, error) {
	var files []fontFile
	for _, path := range paths {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			continue
		}
		font, ok, err := readFont(path)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		files = append(files, font)
	}
	return files, nil
}

func readFont(path string) (fontFile, bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return fontFile{}, false, err
	}
	dir, err := readTableDirectory(data)
	if err != nil {
		return fontFile{}, false, nil
	}
	if _, ok := dir["glyf"]; !ok {
		return fontFile{}, false, nil
	}
	f, err := sfnt.Parse(data)
	if err != nil {
		return fontFile{}, false, nil
	}
	var buf sfnt.Buffer
	family := readName(f, &buf, 16)
	if family == "" {
		family = readName(f, &buf, sfnt.NameIDFamily)
	}
	subfamily := readName(f, &buf, 17)
	if subfamily == "" {
		subfamily = readName(f, &buf, sfnt.NameIDSubfamily)
	}
	family = strings.TrimSpace(family)
	_, variable := dir["fvar"]
	return fontFile{
		path:      path,
		family:    family,
		subfamily: strings.TrimSpace(subfamily),
		variable:  variable,
		kind:      fontKind(data, dir, family),
	}, true, nil
}

func readName(f *sfnt.Font, buf *sfnt.Buffer, id sfnt.NameID) string {
	name, err := f.Name(buf, id)
	if err != nil {
		return ""
	}
	return name
}

type tableRange struct {
	offset uint32
	length uint32
}

func readTableDirectory(data []byte) (map[string]tableRange, error) {
	if len(data) < 12 {
		return nil, errors.New("font data too short")
	}
	version := string(data[0:4])
	switch version {
	case "ttcf":
		return nil, errors.New("font collections are not supported")
	case "OTTO", "true":
	default:
		if binary.BigEndian.Uint32(data[0:4]) != 0x00010000 {
			return nil, fmt.Errorf("unrecognized sfnt version %q", version)
		}
	}
	numTables := int(binary.BigEndian.Uint16(data[4:6]))
	dir := make(map[string]tableRange, numTables)
	for i := 0; i < numTables; i++ {
		offset := 12 + i*16
		if offset+16 > len(data) {
			return nil, errors.New("truncated table directory")
		}
		dir[string(data[offset:offset+4])] = tableRange{
			offset: binary.BigEndian.Uint32(data[offset+8 : offset+12]),
			length: binary.BigEndian.Uint32(data[offset+12 : offset+16]),
		}
	}
	return dir, nil
}

func readTableTags(data []byte) (map[string]bool, error) {
	dir, err := readTableDirectory(data)
	if err != nil {
		return nil, err
	}
	tags := make(map[string]bool, len(dir))
	for tag := range dir {
		tags[tag] = true
	}
	return tags, nil
}

func tableBytes(data []byte, dir map[string]tableRange, tag string) []byte {
	r, ok := dir[tag]
	if !ok {
		return nil
	}
	if uint64(r.offset)+uint64(r.length) > uint64(len(data)) {
		return nil
	}
	return data[r.offset : r.offset+r.length]
}

var monoNamePattern = regexp.MustCompile(`mono|\bcode\b`)

func fontKind(data []byte, dir map[string]tableRange, family string) string {
	lowered := strings.ToLower(family)
	os2 := tableBytes(data, dir, "OS/2")
	post := tableBytes(data, dir, "post")
	fixedPitch := len(post) >= 16 && binary.BigEndian.Uint32(post[12:16]) != 0
	var serifStyle, proportion byte
	if len(os2) >= 42 {
		serifStyle, proportion = os2[33], os2[35]
	}
	if fixedPitch || proportion == 9 || monoNamePattern.MatchString(lowered) {
		return "mono"
	}
	if serifStyle >= 2 && serifStyle <= 10 {
		return "serif"
	}
	if serifStyle >= 11 && serifStyle <= 15 {
		return "sans"
	}
	if strings.Contains(lowered, "serif") && !strings.Contains(lowered, "sans") {
		return "serif"
	}
	return "sans"
}

var variableWordPattern = regexp.MustCompile(`\s+`)

func stripVariable(family string) string {
	stripped := strings.ReplaceAll(family, "Variable", "")
	return strings.TrimSpace(variableWordPattern.ReplaceAllString(stripped, " "))
}

func groupCandidates(files []fontFile) []candidate {
	var candidates []candidate
	byFamily := map[string][]fontFile{}
	for _, f := range files {
		if strings.Contains(strings.ToLower(f.subfamily), "italic") {
			continue
		}
		if f.variable {
			candidates = append(candidates, candidate{
				label:   stripVariable(f.family),
				regular: f.path,
				kind:    f.kind,
			})
			continue
		}
		byFamily[f.family] = append(byFamily[f.family], f)
	}
	for family, group := range byFamily {
		var regular, bold string
		var regularKind string
		for _, f := range group {
			switch strings.ToLower(f.subfamily) {
			case "regular":
				regular = f.path
				regularKind = f.kind
			case "bold":
				bold = f.path
			}
		}
		if regular != "" && bold != "" {
			candidates = append(candidates, candidate{
				label:   family,
				regular: regular,
				bold:    bold,
				kind:    regularKind,
			})
		}
	}
	labelCounts := map[string]int{}
	for _, c := range candidates {
		labelCounts[c.label]++
	}
	for i, c := range candidates {
		if c.bold == "" && labelCounts[c.label] > 1 {
			candidates[i].label = c.label + " (variable)"
		}
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].label != candidates[j].label {
			return candidates[i].label < candidates[j].label
		}
		return candidates[i].regular < candidates[j].regular
	})
	return candidates
}

func familyName(c candidate) string {
	return strings.TrimSuffix(c.label, " (variable)")
}

func outputPath(c candidate, outDir string) string {
	label := familyName(c)
	name := strings.ReplaceAll(label, " ", "") + "-Half.ttf"
	return filepath.Join(outDir, name)
}
