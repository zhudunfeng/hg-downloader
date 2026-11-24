# Windows Runtime Build Contract

## 1. Scope / Trigger

Applies to `.github/workflows/build-runtime.yml` and the packaged Windows GUI/CLI.

## 2. Signatures

- Trigger: `workflow_dispatch`, without inputs or automatic events.
- Build: Python 3.14 x64, `python -m PyInstaller`, entry point `run.py`.
- Output: `dist/hg-downloader-windows-x64.zip`, containing `HG-Downloader/`.
- Smoke command: `HG-Downloader.exe --help`, exit code 0 with usage output.

## 3. Contracts

- Run on `windows-2025` with read-only repository content permissions.
- Pin PyInstaller to `6.22.3`, verified with Python 3.14.4. Version 6.22.0's
  generated spec has invalid doubled quotes for `hide_console`; do not regress.
- Use onedir with `--contents-directory .`: `core.__file__` resolves relative to
  the executable directory, preserving `find_tool()`'s adjacent `tools/` fallback.
- Use `--console --hide-console hide-early`: terminal launches retain CLI output;
  Explorer launches hide the program's own console while opening Tkinter.
- Include Python/Tk dependencies, README, third-party notices and full licenses.
- Copy documentation after freezing; relative `--add-data` sources are resolved
  against the spec directory, which is `build/`, rather than the repository root.
- FFmpeg / FFprobe remain external; describe their installation in the package.
- Upload the ZIP as artifact `hg-downloader-windows-x64`, retaining it 14 days.
- Keep all workflow configuration comments and custom build errors in Chinese.
- Native command failures must terminate the job before compression/upload.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Push, PR, tag or schedule | No build triggered |
| Workflow absent from default branch | Explain why Run workflow is unavailable |
| PyInstaller fails | Fail the job with a Chinese diagnostic |
| Executable missing or CLI smoke fails | Fail before uploading an artifact |
| ZIP missing | Artifact upload fails via `if-no-files-found: error` |
| FFmpeg absent on the user's computer | Existing Chinese tool-not-found error |

## 5. Good / Base / Bad Cases

- Good: manually build, extract the complete directory, double-click the GUI.
- Base: run the executable's `--help` from an existing terminal.
- Bad: copy only the executable; onedir requires all packaged supporting files.

## 6. Tests Required

- Validate YAML, GitHub expressions and PowerShell syntax.
- Assert that the sole event is `workflow_dispatch` and artifact paths agree.
- Build on Windows and run the frozen CLI; check bundled Tcl/Tk and notices.
- Exercise the packaged GUI without network access and close its own process.
- Run the existing offline downloader regression suite when tooling permits.
- Do not retain temporary test classes generated for packaging verification.

## 7. Wrong vs Correct

Wrong: accept PyInstaller's default `_internal/` directory while documenting
FFmpeg in `HG-Downloader/tools/`; the existing `find_tool()` searches elsewhere.

Correct: use `--contents-directory .` so documentation and actual tool lookup
agree, without introducing a separate frozen-runtime code path.
