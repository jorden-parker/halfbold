package main

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type screen int

const (
	screenPick screen = iota
	screenRunning
	screenDone
)

var (
	errorStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("9"))
	helpStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
)

type item struct{ c candidate }

func (i item) Title() string { return i.c.label }

func (i item) Description() string {
	if i.c.bold == "" {
		return "variable font  " + filepath.Base(i.c.regular)
	}
	return "Regular + Bold pair  " + filepath.Base(i.c.regular) + " + " + filepath.Base(i.c.bold)
}

func (i item) FilterValue() string { return i.c.label }

type runDoneMsg struct {
	output string
	err    error
}

type model struct {
	list    list.Model
	spinner spinner.Model
	screen  screen
	runner  runner
	outDir  string
	chosen  candidate
	output  string
	err     error
}

func newModel(candidates []candidate, r runner, outDir string) model {
	items := make([]list.Item, len(candidates))
	for i, c := range candidates {
		items[i] = item{c: c}
	}
	l := list.New(items, list.NewDefaultDelegate(), 0, 0)
	l.Title = "halfbold: pick a font to convert"
	s := spinner.New()
	s.Spinner = spinner.Dot
	return model{
		list:    l,
		spinner: s,
		screen:  screenPick,
		runner:  r,
		outDir:  outDir,
	}
}

func (m model) Init() tea.Cmd {
	return nil
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.list.SetSize(msg.Width, msg.Height-2)
		return m, nil
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
		case "q":
			if m.screen != screenRunning && m.list.FilterState() != list.Filtering {
				return m, tea.Quit
			}
		case "enter":
			switch m.screen {
			case screenPick:
				if m.list.FilterState() != list.Filtering {
					selected, ok := m.list.SelectedItem().(item)
					if !ok {
						return m, nil
					}
					m.chosen = selected.c
					m.screen = screenRunning
					dir := m.outDir
					if dir == "" {
						dir = filepath.Dir(m.chosen.regular)
					}
					out := outputPath(m.chosen, dir)
					return m, tea.Batch(m.spinner.Tick, m.runner.run(m.chosen, out))
				}
			case screenDone:
				m.screen = screenPick
				return m, nil
			}
		case "esc":
			if m.screen == screenDone {
				m.screen = screenPick
				return m, nil
			}
		}
	case spinner.TickMsg:
		if m.screen == screenRunning {
			var cmd tea.Cmd
			m.spinner, cmd = m.spinner.Update(msg)
			return m, cmd
		}
		return m, nil
	case runDoneMsg:
		m.output = msg.output
		m.err = msg.err
		m.screen = screenDone
		return m, nil
	}
	if m.screen == screenPick {
		var cmd tea.Cmd
		m.list, cmd = m.list.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m model) View() string {
	switch m.screen {
	case screenRunning:
		return fmt.Sprintf("%s converting %s …\n", m.spinner.View(), m.chosen.label)
	case screenDone:
		return m.doneView()
	default:
		return m.list.View()
	}
}

func (m model) doneView() string {
	var body string
	if m.err != nil {
		body = errorStyle.Render(lastLines(m.output, 15))
	} else {
		body = m.output + "\nEnable \"calt\" in your app if it is off."
	}
	return body + "\n\n" + helpStyle.Render("enter: back  q: quit")
}

func lastLines(s string, n int) string {
	lines := strings.Split(strings.TrimRight(s, "\n"), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}
