# SE-2026

> **Status:** 🚧 Project setup. The repository foundations are in place and implementation has not started yet.

<!-- TODO: Replace with a one-paragraph description of the project: what it is, who it is for, and the problem it solves. -->
_A short description of the project goes here._

## Table of contents

- [About](#about)
- [Project management](#project-management)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Development workflow](#development-workflow)
- [Documentation](#documentation)
- [Team](#team)
- [License](#license)

## About

| | |
|---|---|
| **Goal** | _TODO: main objective of the project_ |
| **Users** | _TODO: who will use it_ |
| **Scope** | _TODO: what is in scope and out of scope for this release_ |
| **Tech stack** | _TODO: decided in an ADR under [`docs/adr/`](docs/adr/)_ |

## Project management

Planning and tracking happen in **Azure DevOps (Azure Boards)**. GitHub holds the source code and documentation.

- **Work items** (epics, features, user stories, tasks, bugs) are in Azure Boards.
- **Linking:** put `AB#<id>` in a commit message or pull request description to link it to the matching Azure Boards work item, for example `AB#42`. This needs the [Azure Boards app for GitHub](https://learn.microsoft.com/azure/devops/boards/github/) to be installed.
- **GitHub Issues** are used for anything raised directly on GitHub. Templates are in [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/).

<!-- TODO: Add the link to the Azure DevOps project board. -->

## Repository structure

```
.
├── .github/                # Issue and PR templates, code owners
├── docs/                   # Project documentation
│   ├── adr/                # Architecture Decision Records
│   ├── architecture.md     # System overview
│   └── requirements.md     # Functional and non-functional requirements
├── .editorconfig           # Shared editor settings
├── .gitattributes          # Line-ending and file-type rules
├── .gitignore              # Files Git should ignore
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md         # How to contribute (branches, commits, PRs)
├── SECURITY.md             # How to report vulnerabilities
└── README.md
```

Source code and test folders will be added once the tech stack is chosen.

## Getting started

_No code yet. This section will cover prerequisites, installation, configuration and how to run the project and its tests._

```bash
git clone https://github.com/mos26613/SE-2026.git
cd SE-2026
```

## Development workflow

In short: branch from `main`, make small focused commits, open a pull request, get a review, merge. The full rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

| Document | Purpose |
|---|---|
| [docs/requirements.md](docs/requirements.md) | What the system must do |
| [docs/architecture.md](docs/architecture.md) | How the system is structured |
| [docs/adr/](docs/adr/) | Why key technical decisions were made |

## Team

<!-- TODO: Fill in team members and roles. -->
| Name | Role | GitHub |
|---|---|---|
| _TBD_ | _TBD_ | _TBD_ |

## License

_TODO: Choose a license (for example MIT) and add a `LICENSE` file. Until then, all rights are reserved by the authors._
