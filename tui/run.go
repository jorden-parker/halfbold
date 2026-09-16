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
