package main

import (
	"errors"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestItemDescriptionShowsKind(t *testing.T) {
	i := item{c: candidate{kind: "mono", regular: "/f/X.ttf"}}
	if got := i.Description(); !strings.HasPrefix(got, "mono  variable font  ") {
		t.Fatalf("got %q", got)
	}
}

func TestSlotPickEnterUsesDetectedKind(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("s")})
	m2 := updated.(model)
	if m2.screen != screenSlotPick {
		t.Fatalf("expected screenSlotPick, got %v", m2.screen)
	}
	updated, _ = m2.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m3 := updated.(model)
	if m3.screen != screenRunning {
		t.Fatalf("expected screenRunning, got %v", m3.screen)
	}
	if m3.slot != "sans" {
		t.Fatalf("expected slot sans, got %q", m3.slot)
	}
}

func TestSlotPickDigitOverridesKind(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("s")})
	m2 := updated.(model)
	updated, _ = m2.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("3")})
	m3 := updated.(model)
	if m3.slot != "mono" {
		t.Fatalf("expected slot mono, got %q", m3.slot)
	}
}

func TestSlotPickEscReturnsToList(t *testing.T) {
	m := newModel([]candidate{{label: "Inter", regular: "/f/I.ttf", kind: "sans"}}, runner{project: "/repo"}, "", nil)
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("s")})
	m2 := updated.(model)
	updated, _ = m2.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m3 := updated.(model)
	if m3.screen != screenPick {
		t.Fatalf("expected screenPick, got %v", m3.screen)
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
