# Huangguo Video Downloader

## Goal and confirmed user instructions

Implement a working downloader for the supplied `n59j.aqkmowihz.cc` site.
The user authorized researching similar GitHub projects and integrating reusable code.
The selected implementation is a standard-library Python application with a Chinese
Tkinter GUI, a batch CLI, and external FFmpeg / FFprobe.

## Requirements

- Accept video detail URLs, episode URLs, tracking query strings, or numeric video IDs.
- Parse published episodes and allow current-episode, selected-episode, and whole-series downloads.
- Request fresh ordinary playback metadata, download the selected main/HEVC HLS stream,
  save MP4 without transcoding, and validate before publishing the output.
- Support cancellation, retry, existing-file checks, cookies, and batch CLI inputs.
- Reuse appropriate Apache-2.0 UAV-Downloader parsing code with pinned provenance and license.
- Follow AGENTS.md Chinese documentation/type requirements. Python uses colon/indentation
  for blocks; braces cannot replace valid Python syntax.
- Execute regression tests, then remove generated unit-test classes per AGENTS.md,
  retaining test results and reproducible CLI smoke commands in documentation.

## Acceptance criteria

- [x] Target-site metadata returns three published episodes for a verified sample.
- [x] Public HTML fallback and retry cooldown parsing are integrated from UAV-Downloader.
- [x] H.264 and HEVC samples contain valid video and audio.
- [x] A complete real episode is saved and passes FFprobe duration/track validation.
- [x] Local AES-128 HLS integration, missing segments, cancellation, retries, and fallback tests pass.
- [x] GUI parse/select/download workflow succeeds against a local fixture.
- [ ] All retained Python methods have Chinese comments and annotated parameters/returns.
- [ ] Final checks pass; generated unit-test classes are removed and results persisted.
- [ ] Final wheel contains third-party license and provenance documents.

## Constraints and scope

No database or database schema is used. No website uploads, account modifications,
DRM implementation, paid-access bypass, or crawler-wide downloading is part of this task.
The task started with an empty directory; Trellis and AGENTS.md were added during execution.
An existing bootstrap-guidelines task must be left intact.

## Evidence

See `verification.md`, `research/implementation.md`, repository README,
and THIRD_PARTY_NOTICES.md. Live media evidence remains under downloads/verification/.
