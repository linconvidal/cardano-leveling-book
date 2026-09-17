# Cardano Leveling Book

Technical leveling material for Cardano. The reader sees one continuous booklet; authors edit one file per lesson. Portuguese and English contain the same 21-lesson curriculum, with separate saved learner work.

## Build and preview

```sh
uv run build.py
uv run build.py --check
```

`index.html` (Portuguese) and `index-en.html` (English) are generated. Each contains the CSS, JavaScript and all lessons, so the existing static preview and print-to-PDF workflow continue to work. The build uses pinned Jinja2 and PyYAML dependencies through `uv`; it does not need Node, a frontend framework or a bundler.

After editing a source file, run the build and reload the preview. If the existing preview is running, keep using **http://localhost:4173/**. Do not change its hostname or port if you want to retain the same browser storage.

To start a preview on a machine where that port is free:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

The published project URL is https://linconvidal.github.io/cardano-leveling-book/ . Local changes are not automatically deployed there.

## Source files

- `content/pt-BR/aula-0-1.html`, etc.: one lesson body and its metadata per file.
- `content/pt-BR/book.yaml`: document title, language, output filename, module titles/order and short prose summaries, displayed in the contents and at each module opening.
- `content/en/`: equivalent English lesson files, book metadata, introduction, references and UI catalog.
- `content/pt-BR/intro.html`: cover, workshop context and browser execution/storage notes. This template can use `book.title` and the UI catalog.
- `content/pt-BR/references-0.html`, etc.: module reference sections, with their existing IDs.
- `content/pt-BR/ui.json`: buttons, tooltips, navigation labels and runtime messages.
- `shared/layout.html`, `book.html`, `navigation.html`: one set of presentation templates for every language.
- `shared/styles.css`, `app.js`: one stylesheet and one implementation of navigation, quizzes, editors, persistence and Python execution.
- `build.py`: validation and static generation.

Lesson-local SVGs and their embedded styles remain with their content. There is no copy of the editor or quiz implementation in each lesson.

## Edit a lesson

A lesson starts with YAML frontmatter, followed by its original HTML body:

```html
---
title: Do texto aos bytes
map_title: Bytes
summary: Entender por que verificação começa por uma representação exata.
---

<div class="objectives">...</div>
```

Required fields:

- `title`: full lesson heading.
- `map_title`: compact label in the module's reading sequence.
- `summary`: description in the book's contents section.

Optional fields:

- `short_title`: shorter title for both navigation and contents; defaults to `title`.
- `description`: introductory line below the lesson heading.

Do not add an `<article>` wrapper or duplicate the lesson header. Those come from the shared template. Navigation, contents, reading sequences and lesson counts are generated from the same metadata.

The filename supplies the stable anchor and numeric order: `aula-1-9.html` precedes `aula-1-10.html`. Keep existing filenames and activity IDs stable. Module order comes from `book.yaml`.

Lesson bodies are included verbatim, not parsed and rewritten or evaluated as Jinja templates. Literal `{{ ... }}` inside an example stays literal. Keep form markup and starter code intact during structural edits: legacy progress identities depend on that content. Real changes to an exercise intentionally isolate incompatible saved work.

End every lesson with two top-level blocks, outside activities and answers: `.closing` headed **O que aprendemos**, with concrete takeaways in a `<ul>`, then `.bridge` headed **Próxima aula**, introducing the next topic. The final lesson uses **Para continuar** and explicitly states that the guide has ended instead of promising another lesson. English uses **What we learned**, **Next lesson** and **To continue**. Keep these summaries in the lesson source; build tests check their presence, position and bilingual coverage.


## Curriculum destinations

Both books have **21 lessons**: four in M0, thirteen in M1 and four in M2. M0 introduces bytes, hashes, keys and signatures. M1 begins with network and consensus (1.1–1.3), CIPs/governance/parameters (1.4), then Shelley addresses and credentials (1.5), transaction bytes and Ed25519 witnesses (1.6), eUTxO (1.7), fees/validity and CIP-30 (1.8), document metadata (1.9), assets/native scripts (1.10), recovery and explorer verification (1.11), Plutus (1.12), then CIP-68 (1.13).

M2 is now a four-lesson sequence: events/checkpoints (2.1), Merkle inclusion (2.2), batching/costs/Hydra (2.3), privacy/publication (2.4). Each builds on the preceding mechanisms. The document task in 1.9 continues in 1.11; CIP-68 follows Plutus rather than introducing state validation beforehand.

| Previous M2 material | Current destination |
|---|---|
| 2.1 publication and 2.12 privacy | 2.4, including predictable-hash enumeration and private-nonce opening |
| 2.2 Ed25519 | 1.6; library variants remain a short RFC reference |
| 2.3 recovery | Brief wallet/recovery context in 1.5; detailed key-generation compatibility is outside this guide |
| 2.4 wallets/CIP-30 | 1.5–1.8; witness merging and submission in 1.8 |
| 2.5 native scripts/CIP-25 | 1.10; multisig/time exercise and a short media-token section |
| 2.6 CIP-68 | 1.13, after Plutus |
| 2.7 Plutus | 1.12, including effects, validation phases and migration |
| 2.8 Merkle/scaling | 2.2 and 2.3; privacy limitations in 2.4 |
| 2.9 document/hash/reference | Integrated original-file task in 1.9 and 1.11 |
| 2.10 evidence/authority | Brief local limits at the relevant mechanisms, no standalone matrix |
| 2.11 event history | 2.1, with trusted checkpoints and appended corrections |
| 2.13 DPP architecture | Only volume/cost measurement in 2.3 and a Merkle demo reference in 2.2; no taxonomy, personas or replacement appendix |
| 2.14 EAC | Compact supply arithmetic in 1.10; industrial case remains outside this guide |

Old `aula-2-5.html` through `aula-2-14.html` are retired. Numbers 2.1–2.4 now identify the new subjects, not redirects to their previous content. Do not add colliding numeric aliases. The preserved M0 sources contain no references to retired M2 numbers requiring a handoff. Relevant specifications now accompany their destination module in `references-1.html` or `references-2.html`.

Unchanged examples retain their storage identities. New and revised exercises use semantic IDs and revision signatures; incompatible old drafts and passes are not applied, and old localStorage records are not deleted. The local `.before-curriculum-revision-*.zip` backup is ignored and must not be published.

## Portuguese and English

`content/en/` contains the complete translation, configured with `language: en` and `output: index-en.html`. Translate content and the UI catalog, not the shared runtime or stylesheet. Keep lesson filenames, IDs, exercise identities, correct-answer tokens and links aligned across languages.

Python names, comments and feedback are translated. Exact example data remains unchanged where bytes are part of the lesson: JSON keys, hash-input strings, CBOR, signatures, profile/domain identifiers and Merkle E/D proof codes. English glosses explain these retained strings. Translating a frozen string would silently change the demonstrated hash or serialization.

```sh
uv run build.py --lang en
uv run build.py --lang pt-BR
```

Without `--lang`, the build checks and renders all configured books. A language is registered by its `book.yaml`; `--lang pt-BR` can still build Portuguese while the English lesson files are incomplete. There is no automatic fallback to Portuguese text or UI strings.

The chapter menu ends with a centered, native PT/EN selector adapted from the Workbench. Its quieter booklet variant uses plain labels and a small chevron, without flags or a permanent background or visible border. Keyboard focus remains visible, and touch targets stay at least 44 px high. An unavailable language is disabled, not linked to a legacy file. Destinations come from the books generated in the same build. Run `uv run build.py` without `--lang` to generate both versions and enable switching; `--site` does the same for publication staging. A `--lang` build is an isolated preview and leaves the other language unavailable in that generated page, even if an older HTML file exists.

Switching keeps the active lesson or section when it exists in the destination; otherwise it opens the contents. Saved exercises remain separate by document language. The selector follows the menu on mobile and is hidden in print and without JavaScript.

The previous legacy `index-en.html` was backed up and explicitly adopted before replacement with the generated English book. Tests cover both real exports; separate synthetic locale fixtures continue to check missing-language and missing-anchor behavior and are never published.

## GitHub Pages

`.github/workflows/pages.yml` builds from `content/` and `shared/`, runs the build tests, and runs the browser regression suite against the generated `_site/index.html`. Only `_site/` is uploaded. Pull requests to `main` build and test without deploying. Pushes to `main`, or manual workflow runs on `main`, deploy after successful checks. Manual runs on other branches do not deploy.

The publication directory contains only the HTML outputs declared in the configured books and `.nojekyll`. It excludes lesson sources, scripts and backups. Both configured HTML exports are included. All configured languages must validate, and one must output `index.html`. Committed root-level HTML is not used as input or modified by this build.

**Activation requires a repository setting.** On 2026-09-16, the Pages API reported `Deploy from a branch`, using `main` at `/`. Before the first push or merge to `main` with this workflow, the owner must change **Settings > Pages > Build and deployment > Source** to **GitHub Actions**. Otherwise the old branch-based publisher remains active. This change has not been applied; preparing and testing these files does not publish anything.

To build and test the publication artifact locally, without uploading or deploying:

```sh
uv run test-build.py
uv run build.py --site
uv run test-learner-workspace.py --html _site/index.html
```

`--site` requires a new `_site/` directory and refuses to reuse one, preventing stale files from entering a later deployment. To rebuild, inspect the existing directory and move it aside or run `gio trash _site` first. The directory is ignored by Git. `--site` cannot be combined with `--lang`, `--check` or `--adopt`.

The workflow uses Ubuntu 24.04, Python 3.12, uv 0.9.18 and the runner's Chrome. It installs `gio` if needed for safe test cleanup. Browser checks require access to Prism and Pyodide CDNs. Deployment permissions belong only to the deploy job, which targets the `github-pages` environment; repository checkout does not retain credentials. Actions are referenced by commit SHA.

Optional local workflow lint, also without running any GitHub job:

```sh
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.12 .github/workflows/pages.yml
```

## Guardrails and verification

The build rejects duplicate metadata keys and HTML IDs, broken local links, missing UI strings, orphan lessons, invalid output paths and output-name collisions between languages. It renders and validates before writing, checks for concurrent source changes, and replaces output atomically.

Generated files carry a content checksum. A manual edit to a generated file stops the next build rather than being silently overwritten. Move the intended edit into the source first. `--adopt SHA256` is an exceptional, explicit consent to replace an exact legacy or manually edited output after reconciliation; it is not needed in normal use. The checksum detects accidental edits, not adversarial tampering.

```sh
uv run test-build.py
uv run test-learner-workspace.py
```

Browser checks use a private Chrome profile, a loopback fixture server and real Pyodide. They require Chrome and network access to the existing Prism and Pyodide CDNs. They do not use the reader's browser profile.

The local, ignored `.before-refactor-20260916.zip` preserves the pre-extraction files, including both old HTML files. Optional migration audits:

```sh
uv run test-build.py --baseline .before-refactor-20260916.zip
uv run test-learner-workspace.py --baseline .before-refactor-20260916.zip
```

The first audit requires exact historical manuscript content. The second checks restoration of saved work and compares all persistence identities. Both are strict structural-migration audits: later editorial changes can fail these comparisons. Audit intentional exercise revisions separately; old records must remain intact without being applied to incompatible exercises. The regular tests do not freeze the manuscript against future edits. `test-build.py` also loads `test_curriculum.py`: it checks the approved sequence and reference destinations, executes every runnable Python example, and runs each authored validator against a correct repair, its starter and plausible incorrect repairs from `curriculum_test_cases.py`. `test_bilingual.py` checks complete PT/EN structure, shared diagram geometry/runtime, UI coverage, exact Python/validator data and SDK results. `bilingual_test_cases.py` derives identifier correspondence from the actual syntax trees rather than trusting a translation manifest. The browser suite validates the real exercises with Pyodide, in addition to the runtime fixtures. `bilingual_browser_checks.py` executes all 31 English examples, checks all 11 validators against starters/repairs/mistakes, grades all English quizzes, and switches between the actual exports to verify separate drafts and grades.

To audit intentional curriculum revisions against an earlier HTML export, without requiring every identity to remain unchanged:

```sh
uv run test-learner-workspace.py --curriculum-baseline /path/to/previous/index.html
```

This audit uses a separate disposable browser context. It seeds historical drafts and synthetic stale passes, checks that unchanged examples restore them, rejects them for revised examples, restores an unchanged M1 quiz grade and verifies that old records remain intact. `curriculum_browser_checks.py` contains these assertions; it is test-only and is never bundled into the book.

Keep root-level generated HTML and its sources together when committing, so local previews stay current. Pages publishes only `_site/`. `uv run build.py --check` detects stale preview exports without changing files.
