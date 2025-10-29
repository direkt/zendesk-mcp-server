# Repository Guidelines

## Project Structure & Module Organization
- Core source lives in `src/zendesk_mcp_server/`; `server.py` wires MCP prompts/tools and `zendesk_client.py` wraps Zendesk REST calls.
- `pyproject.toml` and `uv.lock` pin dependencies; update both when adding packages.
- Runtime secrets load from `.env` (see `.env.example`); never commit populated `.env`.
- Create new modules beside existing ones and import them in `__init__.py` when they expose CLI surface.

## Build, Test, and Development Commands
- `uv venv && uv pip install -e .` — create a local environment and install in editable mode.
- `uv run zendesk` — launch the MCP server over stdio (used by Claude desktop).
- `uv build` — produce a wheel/sdist before publishing.
- `uv run python -m mcp_cli --list-prompts` — quick smoke test against the server once running.

## Coding Style & Naming Conventions
- Python 3.12, 4-space indentation, type hints for public functions, and `snake_case` for modules, functions, and variables.
- Keep prompt/template constants UPPER_SNAKE_CASE and loggers named after their module (see `server.py:17`).
- Follow PEP 8; if you add tooling (e.g., `ruff`, `black`), commit config in `pyproject.toml`.

## Testing Guidelines
- Place automated tests under `tests/` mirroring the package layout (e.g., `tests/test_server.py`).
- Prefer `pytest` fixtures for async flows; spin up fake Zendesk responses rather than hitting the API.
- Run `uv run pytest` before opening a pull request; aim to cover new prompts/tools and error branches.

## Commit & Pull Request Guidelines
- Match the existing history: short, imperative lowercase subjects (`add create_ticket tool`, `fix logging`).
- Squash noisy work-in-progress commits locally; include issue/PR references like `#123` when relevant.
- Pull requests should explain the customer or agent impact, list manual test steps, and attach screenshots for UX-facing changes (e.g., updated prompt outputs).

## Security & Configuration Tips
- Store Zendesk credentials in `.env`; rotate tokens immediately if exposed.
- Validate environment variables on startup and guard new settings with clear error messages.
- Scrub logs of customer data; avoid logging full ticket payloads outside of debug builds.
