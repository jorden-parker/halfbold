package main

import (
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
