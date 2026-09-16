package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

const fontCaskPrefix = "font-"

type brew struct{}

func brewSearchArgs() []string {
	return []string{"search", "--cask", "font-"}
}

func brewInstallArgs(token string) []string {
	return []string{"install", "--cask", token}
}

func brewInfoArgs(token string) []string {
	return []string{"info", "--cask", "--json=v2", token}
}

func filterFontCaskTokens(lines []string) []string {
	var tokens []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if !strings.HasPrefix(trimmed, fontCaskPrefix) {
			continue
		}
		tokens = append(tokens, trimmed)
	}
	return tokens
}

type caskArtifact struct {
	Font   []string `json:"font"`
	Target string   `json:"target"`
}

type caskInfo struct {
	Casks []struct {
		Token     string         `json:"token"`
		Artifacts []caskArtifact `json:"artifacts"`
	} `json:"casks"`
}

func parseCaskFontTargets(data []byte, fontsDir string) ([]string, error) {
	var info caskInfo
	if err := json.Unmarshal(data, &info); err != nil {
		return nil, err
	}
	if len(info.Casks) == 0 {
		return nil, errors.New("brew info returned no cask")
	}
	var paths []string
	for _, a := range info.Casks[0].Artifacts {
		if len(a.Font) == 0 {
			continue
		}
		if a.Target != "" {
			paths = append(paths, a.Target)
			continue
		}
		paths = append(paths, filepath.Join(fontsDir, filepath.Base(a.Font[0])))
	}
	return paths, nil
}

type brewSearchMsg struct {
	tokens []string
	err    error
}

type brewInstallMsg struct {
	token      string
	candidates []candidate
	output     string
	err        error
}

func (brew) search() tea.Cmd {
	return func() tea.Msg {
		out, err := exec.Command("brew", brewSearchArgs()...).Output()
		if err != nil {
			if ee, ok := err.(*exec.ExitError); ok {
				err = fmt.Errorf("%w: %s", err, strings.TrimSpace(string(ee.Stderr)))
			}
			return brewSearchMsg{err: fmt.Errorf("brew search failed: %w", err)}
		}
		lines := strings.Split(string(out), "\n")
		return brewSearchMsg{tokens: filterFontCaskTokens(lines)}
	}
}

func (brew) install(token, fontsDir string) tea.Cmd {
	return func() tea.Msg {
		out, err := exec.Command("brew", brewInstallArgs(token)...).CombinedOutput()
		if err != nil {
			return brewInstallMsg{token: token, output: string(out), err: err}
		}
		info, err := exec.Command("brew", brewInfoArgs(token)...).Output()
		if err != nil {
			return brewInstallMsg{token: token, output: string(out), err: err}
		}
		paths, err := parseCaskFontTargets(info, fontsDir)
		if err != nil {
			return brewInstallMsg{token: token, output: string(out), err: err}
		}
		files, err := readFonts(paths)
		if err != nil {
			return brewInstallMsg{token: token, output: string(out), err: err}
		}
		return brewInstallMsg{token: token, candidates: groupCandidates(files), output: string(out)}
	}
}
