"""Backward-compatible launcher for older SammyAI commands and documentation."""

from sammyai import CodeEditor, SearchWidget, TextEditor, load_stylesheet, main

__all__ = ["CodeEditor", "SearchWidget", "TextEditor", "load_stylesheet", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
