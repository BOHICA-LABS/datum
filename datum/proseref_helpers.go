package main

// Helpers for story 12b's corpus walk. Separate from corpus.go's walkMD, which takes a filename
// pattern: prose references live in EVERY typed document, not only in the id-named ones.

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// walkAllMD visits every .md file under root, skipping .git, and hands the caller both the
// absolute path and the corpus-relative one.
func walkAllMD(root string, fn func(path, rel string)) {
	_ = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if d.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".md") {
			return nil
		}
		rel, e := filepath.Rel(root, path)
		if e != nil {
			return nil
		}
		fn(path, rel)
		return nil
	})
}

func filepathBase(p string) string { return filepath.Base(p) }

var _ = os.Stat
