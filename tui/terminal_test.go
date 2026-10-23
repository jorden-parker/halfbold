package main

import (
	"strings"
	"testing"
)

func TestEscapeControlsEscapesEveryControlCharacter(t *testing.T) {
	got := escapeControls("\x00\x1b\x07\x7f\u009b\x1f")
	want := `\x00\x1b\x07\x7f\x9b\x1f`
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeControlsEscapesInvalidUTF8Bytes(t *testing.T) {
	got := escapeControls("a\x9bb\xff\xe2\x82")
	want := `a\x9bb\xff\xe2\x82`
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeControlsKeepsPrintableText(t *testing.T) {
	for _, text := range []string{"Inter", "Zürich Sans", "明朝 体", "Emoji 🙂 Mono", "Café Éclair", "�"} {
		if got := escapeControls(text); got != text {
			t.Fatalf("got %q, want %q", got, text)
		}
	}
}

func TestEscapeOutputKeepsColourSequencesAndLines(t *testing.T) {
	text := "\x1b[1m==> Installing\x1b[0m\n\x1b[32;1mok\x1b[m\n"
	if got := escapeOutput(text); got != text {
		t.Fatalf("got %q, want %q", got, text)
	}
}

func TestEscapeOutputEscapesEverythingElse(t *testing.T) {
	got := escapeOutput("\x1b]0;pwned\x07\x1b[2J\x1b[?25l\x1b[38:2::1m\x1b[1m\r")
	want := `\x1b]0;pwned\x07\x1b[2J\x1b[?25l\x1b[38:2::1m` + "\x1b[1m" + `\x0d`
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeEchoedFileNameEscapesOnlyTheFileName(t *testing.T) {
	path := "/out/Evil\x1b]2;x\x07-Half.ttf"
	output := "wrote /out/Evil\x1b]2;x\x07-Half.ttf (3 letter glyphs bolded)\n"
	want := `wrote /out/Evil\x1b]2;x\x07-Half.ttf (3 letter glyphs bolded)` + "\n"
	if got := escapeEchoedFileName(output, path); got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeEchoedFileNameKeepsDirectoryRaw(t *testing.T) {
	path := "/o\x1b/Inter-Half.ttf"
	output := "wrote /o\x1b/Inter-Half.ttf (1 letter glyphs bolded)\n"
	if got := escapeEchoedFileName(output, path); got != output {
		t.Fatalf("got %q, want %q", got, output)
	}
}

func TestEscapeFilePathEscapesBaseNameOnly(t *testing.T) {
	if got := escapeFilePath("/f\x1b/Evil\x1b[2J.ttf"); got != "/f\x1b/Evil\\x1b[2J.ttf" {
		t.Fatalf("got %q", got)
	}
	if got := escapeFilePath("/f/Inter-Bold.ttf"); got != "/f/Inter-Bold.ttf" {
		t.Fatalf("clean path changed: %q", got)
	}
	if got := escapeFilePath(""); got != "" {
		t.Fatalf("empty path became %q", got)
	}
}

func TestEscapeRunOutputEscapesControlsInDirectoryAndKeepsColour(t *testing.T) {
	outPath := "/o\x1b/Inter-Half.ttf"
	output := "wrote /o\x1b/Inter-Half.ttf (1 letter glyphs bolded)\n\x1b[33mwarn\x1b[0m \x1b]0;pwned\x07 Inter\n"
	want := "wrote /o\\x1b/Inter-Half.ttf (1 letter glyphs bolded)\n\x1b[33mwarn\x1b[0m \\x1b]0;pwned\\x07 Inter\n"
	if got := escapeRunOutput(output, outPath); got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeRunOutputEscapesFileNameWithoutColour(t *testing.T) {
	outPath := "/o/\x1b[31mEvil-Half.ttf"
	output := "wrote /o/\x1b[31mEvil-Half.ttf (2 letter glyphs bolded)\n"
	want := `wrote /o/\x1b[31mEvil-Half.ttf (2 letter glyphs bolded)` + "\n"
	if got := escapeRunOutput(output, outPath); got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestEscapeRunOutputKeepsCleanOutputUnchanged(t *testing.T) {
	outPath := "/Users/me/Fonts/Zürich Sans-Half.ttf"
	output := "wrote /Users/me/Fonts/Zürich Sans-Half.ttf (4 letter glyphs bolded)\n"
	if got := escapeRunOutput(output, outPath); got != output {
		t.Fatalf("got %q, want %q", got, output)
	}
}

func TestEscapeRunOutputHostileDirectoryLeavesNoRawEscapeInSuccessBody(t *testing.T) {
	outPath := "/out/a/\x1b]0;pwned\x07b/Evil-Half.ttf"
	output := "wrote " + outPath + " (1 letter glyphs bolded)\n"
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenDone
	m.output = escapeRunOutput(output, outPath)
	view := colorSequence.ReplaceAllString(m.doneView(), "")
	if strings.Contains(view, "\x1b") {
		t.Fatalf("success body has a raw escape: %q", view)
	}
}
