package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
)

type stringList []string

func (s *stringList) String() string {
	return strings.Join(*s, ",")
}

func (s *stringList) Set(value string) error {
	*s = append(*s, value)
	return nil
}

func main() {
	project := flag.String("project", "..", "path to the halfbold repo root")
	outDir := flag.String("out-dir", "", "directory for -Half.ttf output; default is next to the source font")
	list := flag.Bool("list", false, "print discovered candidates and exit")
	var fonts stringList
	flag.Var(&fonts, "fonts", "directory to scan for fonts (repeatable)")
	flag.Parse()

	absProject, err := filepath.Abs(*project)
	if err != nil {
		fmt.Fprintf(os.Stderr, "halfbold-tui: %v\n", err)
		os.Exit(1)
	}
	if _, err := os.Stat(filepath.Join(absProject, "pyproject.toml")); err != nil {
		fmt.Fprintf(os.Stderr, "halfbold-tui: no pyproject.toml in %s; pass -project <repo root>\n", absProject)
		os.Exit(1)
	}

	dirs := []string(fonts)
	if len(dirs) == 0 {
		home, err := os.UserHomeDir()
		if err != nil {
			fmt.Fprintf(os.Stderr, "halfbold-tui: %v\n", err)
			os.Exit(1)
		}
		dirs = []string{filepath.Join(home, "Library", "Fonts")}
	}

	if *outDir != "" {
		if err := os.MkdirAll(*outDir, 0o755); err != nil {
			fmt.Fprintf(os.Stderr, "halfbold-tui: %v\n", err)
			os.Exit(1)
		}
	}

	files, err := scanFonts(dirs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "halfbold-tui: %v\n", err)
		os.Exit(1)
	}
	candidates := groupCandidates(files)
	if len(candidates) == 0 && *list {
		fmt.Fprintf(os.Stderr, "no Regular+Bold pairs or variable TrueType fonts found in %s\n", strings.Join(dirs, ", "))
		os.Exit(1)
	}

	if *list {
		for _, c := range candidates {
			fmt.Printf("%s\t%s\t%s\t%s\n", c.label, c.kind, c.regular, c.bold)
		}
		return
	}

	r := runner{project: absProject}
	m := newModel(candidates, r, *outDir, dirs)
	if _, err := tea.NewProgram(m, tea.WithAltScreen()).Run(); err != nil {
		fmt.Fprintf(os.Stderr, "halfbold-tui: %v\n", err)
		os.Exit(1)
	}
}
