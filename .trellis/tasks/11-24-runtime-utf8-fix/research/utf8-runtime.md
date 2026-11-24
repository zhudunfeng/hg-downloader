# Research: Frozen Windows UTF-8 runtime

- Query: Correct PyInstaller 6.22.3 configuration for Chinese CLI output on an English Windows runner with redirected stdout.
- Scope: Mixed; official PyInstaller/Python documentation, versioned bootloader source and repository workflow.
- Date: 2026-11-24 (Asia/Shanghai).

## Findings

### Minimal correct configuration

Add the following arguments to the existing `$buildOptions` array:

```powershell
# 将 UTF-8 模式写入冻结解释器，避免英文 Windows 重定向输出使用 CP1252。
'--python-option', 'X utf8'
```

The CLI value contains a space and must be one argument. It is a PyInstaller build option which embeds an interpreter run-time option; it is not an argument passed to HG-Downloader.exe.

PyInstaller's official spec-file documentation lists `X utf8` / `X utf8=1` as supported run-time options, specially interpreted by the bootloader before Python initialization. This initializes UTF-8 mode before argparse or any application code runs.

### Versioned source confirmation

Official `v6.22.3/bootloader/src/pyi_pyconfig.c` was read directly:

- Line 191 initializes `options->utf8_mode = -1`, choosing the default based on locale.
- Lines 301-323 parse the embedded `X ` option and explicitly match `utf8` into `options->utf8_mode`.
- Lines 348-357 use `PyPreConfig_InitIsolatedConfig`, assign `config.utf8_mode = runtime_options->utf8_mode`, then call `Py_PreInitialize`.

Therefore merely setting `PYTHONUTF8=1` or `PYTHONIOENCODING=utf-8` in the GitHub job is insufficient for the frozen application's isolated embedded interpreter. These variables affect an ordinary Python process, but the frozen interpreter does not use ordinary Python environment configuration. The embedded option is the appropriate fix for the distributed executable too.

### Python standard-stream behavior

Python 3.14's UTF-8 mode documentation states that stdin, stdout and stderr use UTF-8 in this mode. This includes redirected standard streams, which otherwise use the Windows locale encoding on an English hosted runner. stderr retains `backslashreplace`; stdout retains its documented error behavior.

PyInstaller's spec-file documentation explicitly explains that the frozen interpreter is isolated and most Python environment variables are ignored; its documented run-time options are the supported way to change this behavior.

### Repository application

- `.github/workflows/build-runtime.yml:63-92` defines the PyInstaller `$buildOptions`; insert the UTF-8 option near `--console`.
- `.github/workflows/build-runtime.yml:124-128` invokes `HG-Downloader.exe --help` and checks only the exit code. Extend this smoke check to capture redirected output and verify an expected Chinese phrase, so the original class of failure remains observable.
- `hg_downloader/cli.py:49-50` calls argparse before any custom CLI output handling. Configuring the interpreter before application startup avoids needing duplicate encoding code in CLI and GUI entry points.
- `.trellis/spec/backend/runtime-build-contract.md` should document embedded UTF-8 and redirected Chinese-output verification.

## Official References

- https://pyinstaller.org/en/stable/spec-files.html — Specifying Python Interpreter Options; confirms supported X utf8 and isolation semantics.
- https://docs.python.org/3.14/library/os.html#python-utf-8-mode — Standard-stream behavior under UTF-8 mode.
- https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.22.3/bootloader/src/pyi_pyconfig.c — Explicit UTF-8 parsing and isolated preinitialization in the pinned version.

## Related Specs

- `.trellis/spec/backend/runtime-build-contract.md` — Frozen executable and CI smoke-test contract.
- `.trellis/spec/backend/download-contract.md` — Shared CLI/GUI entry point and Chinese messages.

## Caveats / Not Found

- Documentation/source inspection proves the setting, but rebuilding and running the executable with redirected stdout is still required to verify the final artifact.
- A successful Chinese Windows run is insufficient evidence for English runner compatibility. Assert UTF-8 bytes decode to the expected Chinese help text.
- No dependency upgrade or application-code modification is necessary for this fix.
