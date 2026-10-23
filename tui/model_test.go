package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
)

func TestItemDescriptionShowsKind(t *testing.T) {
	i := item{c: candidate{kind: "mono", regular: "/f/X.ttf"}}
	if got := i.Description(); !strings.HasPrefix(got, "mono  variable font  ") {
		t.Fatalf("got %q", got)
	}
}

func TestPreviewKeyKeepsListAndReturnsCmd(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("p")})
	m2 := updated.(model)
	if m2.screen != screenPick {
		t.Fatalf("expected screenPick, got %v", m2.screen)
	}
	if m2.chosen.label != "Inter" {
		t.Fatalf("expected chosen label Inter, got %q", m2.chosen.label)
	}
	if cmd == nil {
		t.Fatal("expected non-nil cmd")
	}
}

func TestPreviewKeyIgnoredWhileFiltering(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("/")})
	m2 := updated.(model)
	updated, _ = m2.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("p")})
	m3 := updated.(model)
	if m3.chosen.label != "" {
		t.Fatalf("expected chosen label empty, got %q", m3.chosen.label)
	}
}

func TestPreviewDoneErrorShowsDoneScreen(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(previewDoneMsg{err: errors.New("boom")})
	m2 := updated.(model)
	if m2.screen != screenDone {
		t.Fatalf("expected screenDone, got %v", m2.screen)
	}
	if !strings.Contains(m2.output, "boom") {
		t.Fatalf("expected output to contain boom, got %q", m2.output)
	}
}

func TestPreviewDoneSuccessStaysOnList(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(previewDoneMsg{})
	m2 := updated.(model)
	if m2.screen != screenPick {
		t.Fatalf("expected screenPick, got %v", m2.screen)
	}
}

func TestPreviewKeyOnBrewListReturnsCmd(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenBrewPick
	m.brewList.SetItems([]list.Item{caskItem{token: "font-roboto"}})
	updated, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("p")})
	m2 := updated.(model)
	if m2.caskToken != "font-roboto" {
		t.Fatalf("expected caskToken font-roboto, got %q", m2.caskToken)
	}
	if m2.screen != screenBrewPick {
		t.Fatalf("expected screenBrewPick, got %v", m2.screen)
	}
	if cmd == nil {
		t.Fatal("expected non-nil cmd")
	}
}

func TestPreviewKeyOnBrewListIgnoredWhileFiltering(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenBrewPick
	m.brewList.SetItems([]list.Item{caskItem{token: "font-roboto"}})
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("/")})
	m2 := updated.(model)
	updated, _ = m2.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("p")})
	m3 := updated.(model)
	if m3.caskToken != "" {
		t.Fatalf("expected caskToken empty, got %q", m3.caskToken)
	}
}

const hostileLabel = "Evil\x1b]52;c;ZXZpbA==\x07Font\r\n\t\b\x7f\u009b"

const escapedHostileLabel = `Evil\x1b]52;c;ZXZpbA==\x07Font\x0d\x0a\x09\x08\x7f\x9b`

func TestItemTitleEscapesTerminalControls(t *testing.T) {
	i := item{c: candidate{label: hostileLabel}}
	if got := i.Title(); got != escapedHostileLabel {
		t.Fatalf("got %q, want %q", got, escapedHostileLabel)
	}
}

func TestItemTitleLeavesPrintableLabelsUnchanged(t *testing.T) {
	for _, label := range []string{"Inter", "Zürich Sans", "明朝 体", "Emoji 🙂 Mono", "Café Éclair"} {
		if got := (item{c: candidate{label: label}}).Title(); got != label {
			t.Fatalf("got %q, want %q", got, label)
		}
	}
}

func TestItemFilterValueMatchesDisplayedTitle(t *testing.T) {
	i := item{c: candidate{label: hostileLabel}}
	if i.FilterValue() != i.Title() {
		t.Fatalf("FilterValue %q does not match Title %q", i.FilterValue(), i.Title())
	}
}

func TestItemDescriptionEscapesFileNames(t *testing.T) {
	i := item{c: candidate{kind: "sans", regular: "/f/Evil\x1b[2J.ttf"}}
	want := `sans  variable font  Evil\x1b[2J.ttf`
	if got := i.Description(); got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestRunningViewEscapesFontLabel(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenRunning
	m.chosen = candidate{label: hostileLabel}
	view := m.View()
	if !strings.Contains(view, escapedHostileLabel) || strings.Contains(view, "\x1b]52") {
		t.Fatalf("running view not escaped: %q", view)
	}
}

func TestDoneViewKeepsBrewColourInFailureOutput(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenDone
	m.err = errors.New("brew failed")
	m.output = "\x1b[1m==> Installing\x1b[0m"
	want := errorStyle.Render(m.output) + "\n\n" + helpStyle.Render("enter: back  q: quit")
	if view := m.doneView(); view != want {
		t.Fatalf("got %q, want %q", view, want)
	}
}

func TestDoneViewEscapesBrewControlsInFailureOutput(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenDone
	m.err = errors.New("brew failed")
	m.output = "\x1b[1m==> Installing\x1b[0m\n\x1b]0;pwned\x07\rstep two\n"
	view := m.doneView()
	if !strings.Contains(view, `\x1b]0;pwned\x07`) || strings.Contains(view, "\x1b]0;pwned") || !strings.Contains(view, "\x1b[1m==> Installing") {
		t.Fatalf("failure output not escaped as expected: %q", view)
	}
}

func TestDoneViewSuccessShowsRunOutputAsIs(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenDone
	m.output = "wrote /o\x1b/Inter-Half.ttf (1 letter glyphs bolded)\n"
	want := m.output + "\nEnable \"calt\" in your app if it is off."
	if view := m.doneView(); !strings.HasPrefix(view, want) {
		t.Fatalf("success output changed: %q", view)
	}
}

func TestCaskItemEscapesDisplayButKeepsBrewToken(t *testing.T) {
	token := "font-evil\x1b]52;c;x\x07"
	escaped := `font-evil\x1b]52;c;x\x07`
	i := caskItem{token: token}
	if got := i.Title(); got != escaped {
		t.Fatalf("Title got %q, want %q", got, escaped)
	}
	if got := i.Description(); got != "brew install --cask "+escaped {
		t.Fatalf("Description got %q", got)
	}
	if got := i.FilterValue(); got != escaped {
		t.Fatalf("FilterValue got %q, want %q", got, escaped)
	}
	if got := brewInstallArgs(token)[2]; got != token {
		t.Fatalf("brew argument changed: got %q, want %q", got, token)
	}
}

func TestCaskInstallingViewEscapesToken(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenBrewInstalling
	m.caskToken = "font-evil\x1b[2J"
	if view := m.View(); strings.Contains(view, "\x1b[2J") || !strings.Contains(view, `font-evil\x1b[2J`) {
		t.Fatalf("installing view not escaped: %q", view)
	}
}

func TestCaskInstallListTitleEscapesToken(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	candidates := []candidate{{label: "A", regular: "/f/A.ttf", kind: "sans"}, {label: "B", regular: "/f/B.ttf", kind: "sans"}}
	updated, _ := m.Update(brewInstallMsg{token: "font-evil\x1b[2J", candidates: candidates})
	m2 := updated.(model)
	want := `font-evil\x1b[2J installed: pick a font to convert`
	if m2.list.Title != want {
		t.Fatalf("got %q, want %q", m2.list.Title, want)
	}
}

func TestDoneViewEscapesErrorOutput(t *testing.T) {
	m := newModel(nil, runner{project: "/repo"}, "", nil)
	m.screen = screenDone
	m.err = errors.New("boom")
	m.output = "fetch failed\x1b]2;pwned\x07\n"
	view := m.doneView()
	if !strings.Contains(view, `fetch failed\x1b]2;pwned\x07`) || strings.Contains(view, "\x1b]2;pwned") {
		t.Fatalf("error output not escaped: %q", view)
	}
}

func TestListLineEscapesDiscoveredText(t *testing.T) {
	hostile := candidate{label: hostileLabel, kind: "mono", regular: "/f/Evil\x1b[2J.ttf"}
	wantHostile := escapedHostileLabel + "\tmono\t/f/Evil\\x1b[2J.ttf\t"
	if got := listLine(hostile); got != wantHostile {
		t.Fatalf("got %q, want %q", got, wantHostile)
	}
	clean := candidate{label: "Inter", kind: "sans", regular: "/f/Inter.ttf", bold: "/f/Inter-Bold.ttf"}
	if got := listLine(clean); got != "Inter\tsans\t/f/Inter.ttf\t/f/Inter-Bold.ttf" {
		t.Fatalf("clean line changed: %q", got)
	}
}

func TestListLineKeepsDirectoryRaw(t *testing.T) {
	c := candidate{label: "Inter", kind: "sans", regular: "/f\x1b/Evil\x1b[2J.ttf"}
	if got := listLine(c); got != "Inter\tsans\t/f\x1b/Evil\\x1b[2J.ttf\t" {
		t.Fatalf("got %q", got)
	}
}

func TestStartRunRefusesOutputThatResolvesOutsideOutputDirectory(t *testing.T) {
	root := t.TempDir()
	outDir := filepath.Join(root, "out")
	victim := filepath.Join(root, "notes.txt")
	if err := os.Mkdir(outDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(victim, []byte("keep"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(victim, filepath.Join(outDir, "Evil-Half.ttf")); err != nil {
		t.Fatal(err)
	}
	m := newModel(nil, runner{project: "/repo"}, outDir, nil)
	chosen := candidate{label: "Evil", regular: filepath.Join(root, "Evil-Regular.ttf")}
	got, cmd := m.startRun(chosen)
	if cmd != nil {
		t.Fatal("refused run must not start a command")
	}
	if got.screen != screenDone || got.err == nil {
		t.Fatalf("expected error screen, got screen %v err %v", got.screen, got.err)
	}
}
