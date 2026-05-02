# Contributing to AI Telemetry Tracker

First off, thank you for considering contributing to this project! It's people like you that make open-source such a fantastic community to learn, inspire, and create.

## 🛠️ Local Development Setup

To get started, fork the repository and clone it to your local machine:

```bash
git clone https://github.com/<your-username>/ai-telemetry-tracker.git
cd ai-telemetry-tracker/backend
```

Create a virtual environment, activate it, and install the dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## ✨ Code Quality & Formatting

We maintain a high standard for code quality. For the Python backend, we strictly enforce **PEP 8** standards using **Ruff**. 

Before committing your changes, you must run the formatter and linter:

```bash
# Format the code
ruff format .

# Check for linting errors
ruff check .
```

If you submit a Pull Request, our CI pipeline will automatically run Ruff. PRs with linting errors will not be merged.

## 📝 Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) for our commit messages. This allows us to auto-generate changelogs. 

Please format your commit messages as follows:

- `feat:` for new features (e.g., `feat: add support for Anthropic models`)
- `fix:` for bug fixes (e.g., `fix: resolve database locking issue`)
- `docs:` for documentation changes (e.g., `docs: update quick start guide`)
- `style:` for formatting changes (e.g., `style: run ruff formatter`)
- `refactor:` for code refactoring (e.g., `refactor: extract routing logic`)
- `test:` for adding or updating tests (e.g., `test: add unit tests for proxy`)
- `chore:` for maintenance tasks (e.g., `chore: update dependencies`)

## 🚀 Submitting a Pull Request

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes and commit them using Conventional Commits.
3. Push to your fork: `git push origin feature/your-feature-name`
4. Open a Pull Request against our `main` branch.

We will review your PR as quickly as possible. Thanks again for your contribution!
