package main

import (
	"os/exec"

	tea "github.com/charmbracelet/bubbletea"
)

type runner struct {
	project string
}

func (r runner) args(c candidate, out string) []string {
	base := []string{"run", "--project", r.project, "halfbold", c.regular}
	if c.bold != "" {
		base = append(base, c.bold)
	}
	return append(base, "-o", out)
}

func (r runner) run(c candidate, out string) tea.Cmd {
	return func() tea.Msg {
		output, err := exec.Command("uv", r.args(c, out)...).CombinedOutput()
		return runDoneMsg{output: string(output), err: err}
	}
}

func (r runner) previewArgs(c candidate) []string {
	base := []string{"run", "--project", r.project, "halfbold", "--preview", c.regular}
	if c.bold != "" {
		base = append(base, c.bold)
	}
	return append(base, "--wait")
}

func (r runner) preview(c candidate) tea.Cmd {
	return tea.ExecProcess(exec.Command("uv", r.previewArgs(c)...), func(err error) tea.Msg {
		return previewDoneMsg{err: err}
	})
}

func (r runner) webArgs(kind, family string) []string {
	return []string{"run", "--project", r.project, "halfbold", "--" + kind, family}
}

func (r runner) setWeb(kind, family string) tea.Cmd {
	return func() tea.Msg {
		output, err := exec.Command("uv", r.webArgs(kind, family)...).CombinedOutput()
		return runDoneMsg{output: string(output), err: err}
	}
}
