# Bunshō (文章)

A Japanese language learning tool: hiragana, katakana, JLPT N5-N1 kanji and vocabulary, and
spaced-repetition flashcards. Runs as a containerized FastAPI + React web app on a home server.

Status: early development. See `docs/superpowers/specs/` for the design.

## License

The Bunshō source code is released under the MIT License (see `LICENSE`).

Third-party data is **not** covered by it:

- `resources/JLPT_N5_to_N1_Japanese_Vocabulary.apkg` is GPL-3.0 (see `resources/LICENSE` and
  `resources/README.md`). A `content.db` built from it is a derived work.
- Dictionary data comes from `jamdict-data-fix` (JMdict and KANJIDIC2, distributed under the
  [EDRDG licence](https://www.edrdg.org/edrdg/licence.html)). Check those terms before redistributing
  a built `content.db`.
