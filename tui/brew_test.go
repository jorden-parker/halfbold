package main

import (
	"reflect"
	"testing"
)

func TestBrewSearchArgs(t *testing.T) {
	got := brewSearchArgs()
	want := []string{"search", "--cask", "font-"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestBrewInstallArgs(t *testing.T) {
	got := brewInstallArgs("font-inter")
	want := []string{"install", "--cask", "font-inter"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestBrewInfoArgs(t *testing.T) {
	got := brewInfoArgs("font-inter")
	want := []string{"info", "--cask", "--json=v2", "font-inter"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestFilterFontCaskTokensKeepsOnlyFontPrefix(t *testing.T) {
	input := []string{"birdfont", "font-inter", "  font-roboto ", "", "fontforge-app"}
	got := filterFontCaskTokens(input)
	want := []string{"font-inter", "font-roboto"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestParseCaskFontTargetsUsesTarget(t *testing.T) {
	data := []byte(`{"casks":[{"token":"font-inter","artifacts":[{"font":["InterVariable.ttf"],"target":"/f/InterVariable.ttf"},{"font":["extras/otf/Inter-Bold.otf"],"target":"/f/Inter-Bold.otf"}]}]}`)
	got, err := parseCaskFontTargets(data, "/ignored")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := []string{"/f/InterVariable.ttf", "/f/Inter-Bold.otf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestParseCaskFontTargetsFallsBackToFontsDir(t *testing.T) {
	data := []byte(`{"casks":[{"token":"font-firacode","artifacts":[{"font":["ttf/FiraCode-Bold.ttf"]}]}]}`)
	got, err := parseCaskFontTargets(data, "/fonts")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := []string{"/fonts/FiraCode-Bold.ttf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestParseCaskFontTargetsIgnoresNonFontArtifacts(t *testing.T) {
	data := []byte(`{"casks":[{"token":"font-a","artifacts":[{"zap":[{"trash":"x"}]},{"font":["A.ttf"],"target":"/f/A.ttf"}]}]}`)
	got, err := parseCaskFontTargets(data, "/ignored")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := []string{"/f/A.ttf"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestParseCaskFontTargetsRejectsEmptyCasks(t *testing.T) {
	data := []byte(`{"casks":[]}`)
	if _, err := parseCaskFontTargets(data, "/ignored"); err == nil {
		t.Fatal("expected error for empty casks")
	}
}
