# Contributing to pyth-hermes

Thanks for your interest in improving `pyth-hermes`! This guide covers the
local setup and the quality bar that CI enforces.

## Development setup

Requires Python >= 3.9.

```bash
git clone https://github.com/robertruben98/pyth-hermes
cd pyth-hermes
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quality gates

All three must pass locally and in CI before a change is merged:

```bash
ruff check .        # lint + import sorting
mypy                # static type check (strict)
pytest              # unit tests (mocked HTTP, no network)
```

CI runs `ruff` + `mypy --strict` once on Python 3.12 and runs `pytest` across
Python 3.9-3.13.

## Testing

- We follow **test-driven development**: write a failing test first, watch it
  fail, then implement the minimal change to make it pass.
- Unit tests must not hit the network. Mock HTTP with `respx` or
  `httpx.MockTransport`.
- Live tests against the production API live in `tests/test_integration.py` and
  are marked `@pytest.mark.integration` (deselected by default). Run them
  explicitly with:

  ```bash
  pytest -m integration
  ```

## Code style

- Full type hints; `mypy --strict` must pass.
- Public functions, methods, and models get Google-style docstrings
  (Args/Returns/Raises), with an Example block where it aids usage.
- Keep `Optional[...]` rather than PEP 604 `X | None` in runtime-evaluated
  annotations (pydantic model fields, public function signatures) so the code
  keeps working on Python 3.9.

## Commits & pull requests

- Use clear, conventional commit subjects (e.g. `fix:`, `feat:`, `docs:`,
  `test:`).
- Keep commits focused and reasonably small.
- Open a pull request against `main`; ensure CI is green.
- Update `CHANGELOG.md` under the appropriate version heading.

## Releasing

1. Bump the version in `pyproject.toml` and `src/pyth_hermes/__init__.py`.
2. Add a `CHANGELOG.md` entry.
3. Build and verify: `uv build && uvx twine check dist/*`.
