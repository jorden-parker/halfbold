package main

import (
	"reflect"
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

func TestRunnerWebArgs(t *testing.T) {
	r := runner{project: "/repo"}
	got := r.webArgs("mono", "JetBrainsMono Nerd Font")
	want := []string{"run", "--project", "/repo", "halfbold", "--mono", "JetBrainsMono Nerd Font"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}
