# Git branch and commit guidelines

## Branch names

Use the format `<type>/<kebab-case-summary>`. Keep summaries short (3–6 words), lowercase, hyphen-separated. No spaces, no underscores, no slashes inside the summary.

Types:

- `feat/` — new feature or capability
- `fix/` — bug fix
- `chore/` — tooling, config, dependency bumps, build changes
- `refactor/` — internal restructuring with no behavior change
- `docs/` — documentation only
- `test/` — adding or fixing tests
- `perf/` — performance improvement
- `ci/` — CI/CD pipeline changes

Examples of good branch names:

- `feat/oauth-google-login`
- `fix/null-pointer-on-empty-cart`
- `refactor/extract-payment-service`
- `chore/bump-pydantic-to-2`
- `docs/add-api-quickstart`

Avoid:

- Personal prefixes (`john/...`) unless the team convention requires them
- Ticket IDs alone (`PROJ-1234`) — include a human-readable summary too
- Vague summaries (`feat/updates`, `fix/bug`)
- Branch names over ~50 characters

## Commit messages

Subject line: imperative mood, ≤72 characters, no trailing period.

- Good: `Fix race condition in worker shutdown`
- Bad:  `fixed bug` / `Updated some files.`

Body (when needed): wrap at 72, explain *why* the change was made, what alternatives were considered, and any non-obvious constraints. The diff already shows *what* changed.

When asked to generate ONLY a branch name, reply with just the branch name on a single line — no quotes, no explanation, no markdown.
