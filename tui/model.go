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
	screenBrewLoading
	screenBrewPick
	screenBrewInstalling
	screenCaskPick
	screenSlotPick
)

var (
	errorStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("9"))
	helpStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
)

type item struct{ c candidate }

func (i item) Title() string { return i.c.label }

func (i item) Description() string {
	if i.c.bold == "" {
		return i.c.kind + "  variable font  " + filepath.Base(i.c.regular)
	}
	return i.c.kind + "  Regular + Bold pair  " + filepath.Base(i.c.regular) + " + " + filepath.Base(i.c.bold)
}

func (i item) FilterValue() string { return i.c.label }

type caskItem struct{ token string }

func (i caskItem) Title() string       { return i.token }
func (i caskItem) Description() string { return "brew install --cask " + i.token }
func (i caskItem) FilterValue() string { return i.token }

type runDoneMsg struct {
	output string
	err    error
}

type previewDoneMsg struct{ err error }

type model struct {
	list      list.Model
	brewList  list.Model
	spinner   spinner.Model
	screen    screen
	runner    runner
	brew      brew
	outDir    string
	dirs      []string
	fontsDir  string
	caskToken string
	chosen    candidate
	slot      string
	output    string
	err       error
	width     int
	height    int
}

const pickTitle = "halfbold: pick a font to convert"

func itemsFor(candidates []candidate) []list.Item {
	items := make([]list.Item, len(candidates))
	for i, c := range candidates {
		items[i] = item{c: c}
	}
	return items
}

func newModel(candidates []candidate, r runner, outDir string, dirs []string) model {
	l := list.New(itemsFor(candidates), list.NewDefaultDelegate(), 0, 0)
	l.Title = pickTitle
	brewList := list.New(nil, list.NewDefaultDelegate(), 0, 0)
	brewList.Title = "halfbold: pick a Homebrew font cask to install"
	s := spinner.New()
	s.Spinner = spinner.Dot
	fontsDir := ""
	if len(dirs) > 0 {
		fontsDir = dirs[0]
	}
	return model{
		list:     l,
		brewList: brewList,
		spinner:  s,
		screen:   screenPick,
		runner:   r,
		outDir:   outDir,
		dirs:     dirs,
		fontsDir: fontsDir,
	}
}

func (m model) Init() tea.Cmd {
	return nil
}

func (m model) startRun(c candidate) (model, tea.Cmd) {
	m.chosen = c
	m.slot = ""
	m.screen = screenRunning
	dir := m.outDir
	if dir == "" {
		dir = filepath.Dir(m.chosen.regular)
	}
	out := outputPath(m.chosen, dir)
	return m, tea.Batch(m.spinner.Tick, m.runner.run(m.chosen, out))
}

func (m model) startSetWeb(kind string) (model, tea.Cmd) {
	m.slot = kind
	m.screen = screenRunning
	return m, tea.Batch(m.spinner.Tick, m.runner.setWeb(kind, familyName(m.chosen)))
}

func (m model) showAllFonts() (model, tea.Cmd) {
	m.screen = screenPick
	m.slot = ""
	files, err := scanFonts(m.dirs)
	if err == nil {
		m.list.SetItems(itemsFor(groupCandidates(files)))
	}
	m.list.Title = pickTitle
	m.list.ResetFilter()
	m.list.ResetSelected()
	return m, nil
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.list.SetSize(msg.Width, msg.Height-3)
		m.brewList.SetSize(msg.Width, msg.Height-3)
		return m, nil
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			return m, tea.Quit
		case "q":
			filtering := (m.screen == screenPick || m.screen == screenCaskPick) && m.list.FilterState() == list.Filtering
			filtering = filtering || (m.screen == screenBrewPick && m.brewList.FilterState() == list.Filtering)
			busy := m.screen == screenRunning || m.screen == screenBrewLoading || m.screen == screenBrewInstalling
			if !busy && !filtering {
				return m, tea.Quit
			}
		case "i":
			if m.screen == screenPick && m.list.FilterState() != list.Filtering {
				m.screen = screenBrewLoading
				return m, tea.Batch(m.spinner.Tick, m.brew.search())
			}
		case "s":
			if m.screen == screenPick && m.list.FilterState() != list.Filtering {
				selected, ok := m.list.SelectedItem().(item)
				if !ok {
					return m, nil
				}
				m.chosen = selected.c
				m.screen = screenSlotPick
				return m, nil
			}
		case "p":
			switch {
			case (m.screen == screenPick || m.screen == screenCaskPick) && m.list.FilterState() != list.Filtering:
				selected, ok := m.list.SelectedItem().(item)
				if !ok {
					return m, nil
				}
				m.chosen = selected.c
				return m, m.runner.preview(selected.c)
			case m.screen == screenBrewPick && m.brewList.FilterState() != list.Filtering:
				selected, ok := m.brewList.SelectedItem().(caskItem)
				if !ok {
					return m, nil
				}
				m.caskToken = selected.token
				return m, m.runner.previewCask(selected.token)
			}
		case "1", "2", "3":
			if m.screen == screenSlotPick {
				return m.startSetWeb(map[string]string{"1": "sans", "2": "serif", "3": "mono"}[msg.String()])
			}
		case "enter":
			switch m.screen {
			case screenPick:
				if m.list.FilterState() != list.Filtering {
					selected, ok := m.list.SelectedItem().(item)
					if !ok {
						return m, nil
					}
					return m.startRun(selected.c)
				}
			case screenSlotPick:
				return m.startSetWeb(m.chosen.kind)
			case screenBrewPick:
				if m.brewList.FilterState() != list.Filtering {
					selected, ok := m.brewList.SelectedItem().(caskItem)
					if !ok {
						return m, nil
					}
					m.caskToken = selected.token
					m.screen = screenBrewInstalling
					return m, tea.Batch(m.spinner.Tick, m.brew.install(m.caskToken, m.fontsDir))
				}
			case screenCaskPick:
				if m.list.FilterState() != list.Filtering {
					selected, ok := m.list.SelectedItem().(item)
					if !ok {
						return m, nil
					}
					return m.startRun(selected.c)
				}
			case screenDone:
				return m.showAllFonts()
			}
		case "esc":
			switch m.screen {
			case screenDone:
				return m.showAllFonts()
			case screenSlotPick:
				m.screen = screenPick
				return m, nil
			case screenBrewPick:
				if m.brewList.FilterState() != list.Filtering {
					m.screen = screenPick
					return m, nil
				}
			case screenCaskPick:
				if m.list.FilterState() != list.Filtering {
					return m.showAllFonts()
				}
			}
		}
	case spinner.TickMsg:
		switch m.screen {
		case screenRunning, screenBrewLoading, screenBrewInstalling:
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
	case previewDoneMsg:
		if msg.err != nil {
			m.err = msg.err
			m.output = "preview failed: " + msg.err.Error()
			m.screen = screenDone
		}
		return m, nil
	case brewSearchMsg:
		if msg.err != nil {
			m.err = msg.err
			m.output = msg.err.Error()
			m.screen = screenDone
			return m, nil
		}
		items := make([]list.Item, len(msg.tokens))
		for i, token := range msg.tokens {
			items[i] = caskItem{token: token}
		}
		cmd := m.brewList.SetItems(items)
		m.brewList.ResetFilter()
		m.brewList.ResetSelected()
		m.screen = screenBrewPick
		return m, cmd
	case brewInstallMsg:
		if files, err := scanFonts(m.dirs); err == nil {
			m.list.SetItems(itemsFor(groupCandidates(files)))
		}
		if msg.err != nil {
			output := msg.output
			if output == "" {
				output = msg.err.Error()
			}
			m.output = output
			m.err = msg.err
			m.screen = screenDone
			return m, nil
		}
		if len(msg.candidates) == 0 {
			m.err = fmt.Errorf("%s installed no convertible TrueType font (OTF-only or italic-only cask)", msg.token)
			m.output = m.err.Error()
			m.screen = screenDone
			return m, nil
		}
		if len(msg.candidates) == 1 {
			return m.startRun(msg.candidates[0])
		}
		m.list.SetItems(itemsFor(msg.candidates))
		m.list.Title = msg.token + " installed: pick a font to convert"
		m.list.ResetFilter()
		m.list.ResetSelected()
		m.screen = screenCaskPick
		return m, nil
	}
	switch m.screen {
	case screenPick, screenCaskPick:
		var cmd tea.Cmd
		m.list, cmd = m.list.Update(msg)
		return m, cmd
	case screenBrewPick:
		var cmd tea.Cmd
		m.brewList, cmd = m.brewList.Update(msg)
		return m, cmd
	}
	return m, nil
}

func (m model) View() string {
	switch m.screen {
	case screenRunning:
		if m.slot != "" {
			return fmt.Sprintf("%s setting %s font to %s …\n", m.spinner.View(), m.slot, m.chosen.label)
		}
		return fmt.Sprintf("%s converting %s …\n", m.spinner.View(), m.chosen.label)
	case screenDone:
		return m.doneView()
	case screenBrewLoading:
		return fmt.Sprintf("%s searching Homebrew font casks …\n", m.spinner.View())
	case screenBrewInstalling:
		return fmt.Sprintf("%s brew install --cask %s …\n", m.spinner.View(), m.caskToken)
	case screenBrewPick:
		return m.brewList.View() + "\n" + helpStyle.Render("enter: install  p: preview  /: filter  esc: back  q: quit")
	case screenCaskPick:
		return m.list.View()
	case screenSlotPick:
		return fmt.Sprintf("Use \"%s Half\" on web pages as:\n\n", m.chosen.label) +
			helpStyle.Render(fmt.Sprintf("  1: sans   2: serif   3: mono   enter: %s   esc: back", m.chosen.kind))
	default:
		return m.list.View() + "\n" + helpStyle.Render("enter: convert  p: preview  s: use on web  i: install from Homebrew  /: filter  q: quit")
	}
}

func (m model) doneView() string {
	var body string
	if m.err != nil {
		body = errorStyle.Render(lastLines(m.output, 15))
	} else if m.slot != "" {
		body = m.output + "\nThe extension reloads itself within 30 seconds."
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
