# tests/

One test file per `src/` module, named `test_<module>.py` (e.g.
`src/services/ssh.py` → `test_ssh.py`,
`src/capabilities/server_manager/domain.py` →
`test_server_manager_domain.py`). `conftest.py` holds one autouse fixture
(`log_dir`) that points `errors.py` at a throwaway directory for every
test, so nothing writes into the real `.logs/` as a side effect of
running the suite.

## Conventions

- Prefer a real temp file over mocking the filesystem: `tmp_path` (a
  built-in pytest fixture) plus a small `_write()`/`_config()` helper
  that serializes JSON to it - see `test_app_config.py`. Exercises the
  real loader, not a stand-in for it.
- Mock at the network/subprocess boundary, not above it:
  `unittest.mock.patch("src.module.path.function", ...)` for things
  that would otherwise hit SMTP, SSH, or a real MCP connection (see
  `test_server_manager_domain.py`). The
  string target has to match the real post-flatten import path
  (`src.foo.bar`, not `mcp_server.foo.bar`).
- `dataclasses.replace(settings, field=...)` to override one `Settings`
  field for a test, rather than monkeypatching individual attributes -
  see `test_errors.py`. `Settings` is a
  frozen dataclass, so this is the only way to get a modified copy.
- Test names read as a sentence describing the property under test
  (`test_transport_failure_is_numbered`, not
  `test_failure_2`) - a failing test's name should say what broke
  without reading its body.

## Adding a test file

New module under `src/` → new `test_<same name>.py` here, following
whichever existing file covers the closest kind of module (a capability
domain module → `test_server_manager_domain.py`; an HTTP route
module → `test_command_routes.py`; an services
client → `test_ssh.py`/`test_email.py`).
