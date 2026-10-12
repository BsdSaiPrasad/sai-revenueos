# Repository Guidelines

## Project Structure & Module Organization

This repository contains the SAI RevenueOS architecture, completed implementation through P1.5, and a P1.6 connector implementation awaiting authenticated verification. Keep the root focused on project metadata and navigation. Shared cross-project definitions belong in `shared/contracts/`; project-specific work belongs under `projects/<project-name>/`; repository-wide learning and architecture guides belong in `docs/`.

When application code is introduced, use clear project-local `src/` and `tests/` directories and mirror source paths in tests where practical. Do not create empty folders for future projects or phases.

Avoid committing generated output, local environments, editor settings, credentials, or large datasets. Add these paths to `.gitignore` when the relevant tooling is introduced.

## Build, Test, and Development Commands

The P1.2–P1.6 references use Python 3.9+ and the standard library. Run the credential-free checks with:

```bash
python3 projects/01-data-foundation/scripts/validate_architecture.py
python3 -m unittest discover -s projects/01-data-foundation/tests -v
python3 projects/01-data-foundation/scripts/demo_source_model.py
python3 projects/01-data-foundation/scripts/demo_field_authority.py
python3 projects/01-data-foundation/scripts/demo_synthetic_data.py
python3 projects/01-data-foundation/scripts/demo_live_ingestion.py
```

When a build system is added, provide a small, documented command surface—preferably through a `Makefile` or package scripts. Recommended targets are:

- `make setup` — install development dependencies.
- `make test` — run the complete automated test suite.
- `make lint` — run formatting and static checks.
- `make run` — start the project locally.

Keep this section synchronized with the actual commands; contributors should not need to inspect CI configuration to discover basic workflows.

## Documentation Guidelines

Use plain English before technical terminology. Explain acronyms when first introduced. Use small synthetic business examples for important architecture concepts and decisions. Preserve technical accuracy and verified status.

Apply this rule to Projects 1–7. Clearly distinguish architecture that has been designed from software that has been implemented and executed. Reuse the fictional companies and people defined in `docs/START_HERE.md` so examples remain consistent. Never describe synthetic examples as real customers or production results.

## Coding Style & Naming Conventions

Use the formatter and linter standard for the chosen language, and commit their configuration with the first implementation. Default to spaces, UTF-8, LF line endings, and a final newline. Use descriptive names: `snake_case` for Python modules and functions, `kebab-case` for documentation filenames, and language-standard conventions elsewhere. Favor small modules with explicit responsibilities over broad utility files.

## Testing Guidelines

Add tests with every behavior change and bug fix. Place unit tests under `tests/`, name them after the behavior or module under test, and keep fixtures minimal. Tests must be deterministic and must not depend on live credentials, production services, or execution order. Document any coverage threshold once a test framework is selected.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects such as `Add campaign ingestion pipeline`; optional prefixes like `feat:`, `fix:`, and `docs:` are encouraged when applied consistently. Keep commits focused.

Pull requests should explain the problem, summarize the solution, list verification performed, and link relevant issues. Include screenshots or sample output for user-visible changes, and call out configuration changes, migrations, or follow-up work explicitly.
