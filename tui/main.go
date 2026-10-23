package main

import (
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
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

func listLine(c candidate) string {
	return strings.Join([]string{escapeControls(c.label), c.kind, escapeFilePath(c.regular), escapeFilePath(c.bold)}, "\t")
}

func describeScanError(err error, dirs []string) string {
	var pathErr *fs.PathError
	if !errors.As(err, &pathErr) || slices.Contains(dirs, pathErr.Path) {
		return err.Error()
	}
	return fmt.Sprintf("%s %s: %v", pathErr.Op, escapeFilePath(pathErr.Path), pathErr.Err)
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
		fmt.Fprintf(os.Stderr, "halfbold-tui: %s\n", describeScanError(err, dirs))
		os.Exit(1)
	}
	candidates := groupCandidates(files)
	if len(candidates) == 0 && *list {
		fmt.Fprintf(os.Stderr, "no Regular+Bold pairs or variable TrueType fonts found in %s\n", strings.Join(dirs, ", "))
		os.Exit(1)
	}

	if *list {
		for _, c := range candidates {
			fmt.Println(listLine(c))
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
