package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestRunnerArgsVariable(t *testing.T) {
	r := runner{project: "/repo"}
	c := candidate{label: "Inter", regular: "/fonts/InterVariable.ttf"}
	got := r.args(c, "/fonts/Inter-Half.ttf")
	want := []string{"run", "--project", "/repo", "halfbold", "/fonts/InterVariable.ttf", "-o", "/fonts/Inter-Half.ttf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestRunnerArgsPair(t *testing.T) {
	r := runner{project: "/repo"}
	c := candidate{label: "Mono", regular: "/fonts/Mono-Regular.ttf", bold: "/fonts/Mono-Bold.ttf"}
	got := r.args(c, "/fonts/Mono-Half.ttf")
	want := []string{"run", "--project", "/repo", "halfbold", "/fonts/Mono-Regular.ttf", "/fonts/Mono-Bold.ttf", "-o", "/fonts/Mono-Half.ttf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestRunnerPreviewArgsVariable(t *testing.T) {
	r := runner{project: "/repo"}
	c := candidate{label: "Inter", regular: "/fonts/InterVariable.ttf"}
	got := r.previewArgs(c)
	want := []string{"run", "--project", "/repo", "halfbold", "--preview", "/fonts/InterVariable.ttf", "--wait"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestRunnerPreviewArgsPair(t *testing.T) {
	r := runner{project: "/repo"}
	c := candidate{label: "Mono", regular: "/fonts/Mono-Regular.ttf", bold: "/fonts/Mono-Bold.ttf"}
	got := r.previewArgs(c)
	want := []string{"run", "--project", "/repo", "halfbold", "--preview", "/fonts/Mono-Regular.ttf", "/fonts/Mono-Bold.ttf", "--wait"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestRunnerPreviewCaskArgs(t *testing.T) {
	r := runner{project: "/repo"}
	got := r.previewCaskArgs("font-roboto")
	want := []string{"run", "--project", "/repo", "halfbold", "--preview-cask", "font-roboto", "--wait"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestRunnerRunEscapesEchoedFileNameAndKeepsArguments(t *testing.T) {
	bin := t.TempDir()
	argsFile := filepath.Join(bin, "args.txt")
	script := "#!/bin/sh\nprintf 'warn \\033]0;x\\007\\n'\nprintf '%s\\n' \"$@\" | tee '" + argsFile + "'\n"
	if err := os.WriteFile(filepath.Join(bin, "uv"), []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	out := "/o/Evil\x1b]2;x\x07-Half.ttf"
	msg := runner{project: "/repo"}.run(candidate{regular: "/f/Evil.ttf"}, out)().(runDoneMsg)
	if msg.err != nil {
		t.Fatalf("unexpected error: %v", msg.err)
	}
	if !strings.Contains(msg.output, `/o/Evil\x1b]2;x\x07-Half.ttf`) || strings.Contains(msg.output, "\x1b]2;x") {
		t.Fatalf("echoed file name not escaped: %q", msg.output)
	}
	if !strings.Contains(msg.output, `warn \x1b]0;x\x07`) || strings.Contains(msg.output, "\x1b]0;x") {
		t.Fatalf("other run output control not escaped: %q", msg.output)
	}
	args, err := os.ReadFile(argsFile)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(args), out) {
		t.Fatalf("uv argument changed: %q", args)
	}
}
