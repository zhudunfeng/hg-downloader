# Research: Manual Windows runtime build

- Query: Minimal manual GitHub Actions build for the existing Python GUI/CLI.
- Scope: Mixed, official upstream references and current project code.
- Date: 2026-11-24 (Asia/Shanghai).

## Findings

### Existing code and contracts

- `run.py:1` imports `hg_downloader.cli.main`; preserve this shared entry point.
- `hg_downloader/cli.py:49` defines the CLI entry. With no arguments or `--gui`, it imports `hg_downloader.gui.run` and starts the GUI (`cli.py:51-54`).
- `hg_downloader/core.py:359-382` discovers FFmpeg/FFprobe through explicit paths, sibling tools, PATH and `Path(__file__).resolve().parents[1] / "tools"`.
- `pyproject.toml` requires Python >=3.10 and has no external application dependencies.
- `README.md` and `.trellis/spec/backend/download-contract.md` explicitly keep FFmpeg/FFprobe external.
- CodeGraph queries for `main`, `resolve_tool`, and `find_tool` were attempted; its current index did not expose the target application symbols, so direct source reads confirmed the paths above.

### GitHub Actions

- Official `actions/checkout`, `actions/setup-python`, and `actions/upload-artifact` main READMEs all show their `@v7` major tags. Each corresponding `v7/action.yml` was fetched successfully and declares Node 24. Use `@v7`; no exact latest patch release is asserted.
- Configure only `workflow_dispatch`, without push, pull_request, schedule, or release events.
- GitHub requires the workflow file to exist on the default branch for manual dispatch. Document pushing the workflow to that branch before looking for Run workflow.
- Request only `contents: read`; checkout does not need to persist credentials for this task.
- Upload the complete onedir directory. Set `if-no-files-found: error` so a missing build cannot silently succeed.
- Official Windows Server 2022 image documentation was reachable and reports image version `20261116.370.1`. The parent also verified the Windows 2025 official image; either explicit currently supported x64 Windows runner can build this application.

Official sources verified:

- https://raw.githubusercontent.com/actions/checkout/main/README.md
- https://raw.githubusercontent.com/actions/checkout/v7/action.yml
- https://raw.githubusercontent.com/actions/setup-python/main/README.md
- https://raw.githubusercontent.com/actions/setup-python/v7/action.yml
- https://raw.githubusercontent.com/actions/upload-artifact/main/README.md
- https://raw.githubusercontent.com/actions/upload-artifact/v7/action.yml
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch
- https://raw.githubusercontent.com/actions/runner-images/main/images/windows/Windows2022-Readme.md

### PyInstaller and portable layout

- Local `python -m PyInstaller --version` returns `6.22.0`; local Python is `3.14.4`. Pin the tested PyInstaller version for the build instead of following unbounded upgrades.
- PyInstaller supports Windows console executables and its built-in `_tkinter` hook collects Tcl/Tk data. Static import analysis can follow the import inside `main`; a hidden import should be added only if a verified build reveals a need.
- `--console --hide-console hide-early` keeps console functionality. The bootloader hides the console only when the program owns it, such as an Explorer launch; invoking the executable from an existing terminal keeps CLI output available.
- `--onedir --contents-directory .` uses the flat layout, putting Python support files alongside the executable. Frozen module `__file__` is rooted at the bundle directory. Therefore the existing `core.py` lookup resolves to the executable-adjacent `tools` directory, with no application code change.
- Use this flat onedir bundle, include README, THIRD_PARTY_NOTICES.md, and `licenses/`, and upload the complete directory. Users must extract the complete artifact rather than move the exe alone.
- Keep FFmpeg external. Document adding its bin directory to PATH or placing `ffmpeg.exe` and `ffprobe.exe` in the extracted bundle's `tools/` directory.
- Verify `--help` from an existing terminal and launch the frozen GUI; do not rely solely on successful packaging.

Official sources verified:

- https://pyinstaller.org/en/stable/usage.html (`--hide-console`, `--contents-directory`, and `--onedir`)
- https://pyinstaller.org/en/stable/runtime-information.html (frozen `__file__` and bundle location)
- https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.22.0/PyInstaller/hooks/hook-_tkinter.py

## Related specs

- `.trellis/spec/backend/download-contract.md`: GUI/CLI contract and external FFmpeg dependency.
- `.trellis/spec/guides/code-reuse-thinking-guide.md`: reuse the entry point and external-tool resolution.
- `AGENTS.md`: Chinese configuration explanations and logs, and remove generated unit-test classes after verification.

## Caveats / Not Found

- GitHub unauthenticated release API requests were rate limited. Exact latest action patch versions were not verified and are intentionally omitted.
- Pin 6.22.3, verified locally with the same workflow commands. Copy README and licenses after packaging: relative add-data sources would otherwise resolve against the generated build/ spec directory.
- The complete workflow has to run on GitHub to validate hosted-runner execution and artifact upload; local package smoke checks can validate application behavior beforehand.
