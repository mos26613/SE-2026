# Contributing

Thanks for contributing to SE-2026. This guide explains how we work.

## Before you start

1. Check that there is a work item in **Azure Boards** (or a GitHub issue) for the change. If there isn't, create one.
2. Assign it to yourself and move it to **Active / In Progress**.

## Branches

`main` is always stable and is only changed through pull requests.

Name branches `<type>/<work-item-id>-<short-description>`:

| Type | Use for |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `chore/` | Tooling, config, dependencies |
| `refactor/` | Code changes that don't change behaviour |
| `test/` | Adding or improving tests |

Example: `feature/42-user-login`

## Commits

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary>

<optional body: what and why>

AB#<work-item-id>
```

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`.
- Keep the summary under ~72 characters and in the imperative mood ("add", not "added").
- `AB#<id>` links the commit to the Azure Boards work item.

Example:

```
feat(auth): add login form validation

AB#42
```

## Pull requests

1. Keep PRs small and focused on one work item.
2. Fill in the [PR template](.github/pull_request_template.md), including `AB#<id>`.
3. Make sure the build and tests pass (once CI exists).
4. At least **one approving review** is needed before merging.
5. Resolve all review comments before merging.
6. Prefer **squash merge**, and delete the branch afterwards.

## Code review

Reviewers check:

- The change does what the work item describes.
- The code is readable and consistent with the rest of the project.
- Tests cover the change.
- Documentation (README, `docs/`, ADRs) is updated where needed.

Be kind and specific, and explain the reason behind a suggestion.

## Architecture decisions

Significant technical decisions (language, framework, database, hosting, major patterns) are recorded as an ADR in [`docs/adr/`](docs/adr/). Copy [`template.md`](docs/adr/template.md), give it the next number, and open a PR for discussion.

## Definition of Done

A work item is done when:

- [ ] The code is merged into `main`.
- [ ] Tests are written and passing.
- [ ] The code has been reviewed and approved.
- [ ] Documentation is updated.
- [ ] The work item is closed in Azure Boards.
