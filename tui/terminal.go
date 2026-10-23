package main

import (
	"fmt"
	"path/filepath"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

var colorSequence = regexp.MustCompile(`\x1b\[[0-9;]*m`)

func escapeControls(s string) string {
	var b strings.Builder
	for s != "" {
		s = s[writeEscapedRune(&b, s):]
	}
	return b.String()
}

func writeEscapedRune(b *strings.Builder, s string) int {
	r, size := utf8.DecodeRuneInString(s)
	switch {
	case r == utf8.RuneError && size == 1:
		fmt.Fprintf(b, `\x%02x`, s[0])
	case unicode.IsControl(r):
		fmt.Fprintf(b, `\x%02x`, r)
	default:
		b.WriteString(s[:size])
	}
	return size
}

func escapeLines(s string) string {
	lines := strings.Split(s, "\n")
	for i, line := range lines {
		lines[i] = escapeControls(line)
	}
	return strings.Join(lines, "\n")
}

func escapeOutput(s string) string {
	var b strings.Builder
	last := 0
	for _, span := range colorSequence.FindAllStringIndex(s, -1) {
		b.WriteString(escapeLines(s[last:span[0]]))
		b.WriteString(s[span[0]:span[1]])
		last = span[1]
	}
	b.WriteString(escapeLines(s[last:]))
	return b.String()
}

func escapeFilePath(path string) string {
	if path == "" {
		return ""
	}
	name := filepath.Base(path)
	return strings.TrimSuffix(path, name) + escapeControls(name)
}

func escapeEchoedFileName(output, path string) string {
	name := filepath.Base(path)
	return strings.ReplaceAll(output, name, escapeControls(name))
}

func escapeRunOutput(output, outPath string) string {
	return escapeOutput(escapeEchoedFileName(output, outPath))
}
