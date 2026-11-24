# Video Download Contract

## 1. Scope / Trigger

This contract applies to `hg_downloader/core.py`, its CLI and Tkinter consumers,
and the adapted public-page parser. The application uses no database.

## 2. Signatures

```python
parse_ref(value: str, site: str = DEFAULT_SITE) -> VideoRef
SiteClient.video(ref: VideoRef) -> Video
SiteClient.playback(ref: VideoRef, episode: Episode, stream: str) -> tuple[str, dict[str, str]]
Downloader.download(video: Video, episode: Episode) -> Path
```

CLI: `python run.py URL_OR_ID [--all | -e 1,3-5] [-o DIRECTORY]`.
`--list --json` writes only JSON to stdout; diagnostics belong on stderr.
No CLI arguments opens the GUI.

## 3. Contracts

- Detail URLs use `/video/{positive_id}/` or `/video/{positive_id}/ep-{positive_ep}/`.
  Tracking queries/fragments are removed; the supplied mirror origin is preserved.
- Metadata: `GET /api/videos/{id}` yields `data.title` and `data.episodes` rows with
  `ep_num`, `title`, `duration`, and `status=1`. Selected missing episodes are errors.
- Playback: `POST /api/videos/{id}/episodes/{ep}/playback`, JSON body `{}`.
  Response `data.id`, `data.ep`, and `manifest_method=GET` must match expectations.
  Use `streams.main` or `streams.hevc` explicitly; never substitute `preview`.
- Dynamic CDN headers come from the playback response; do not hardcode their values
  or persist signed media URLs. User cookies remain scoped to the website API.
- `Options` fields must have Chinese comments explaining defaults and behavior.
- Download events cross the service/UI boundary through a thread-safe queue.
  Workers do no Tk calls; the Tk main thread drains events and changes controls.
- FFmpeg and FFprobe are external executables. API/network waits and FFmpeg read
  waits are bounded; cancellation terminates and reaps the process.
- Publish a validated temporary output atomically; preserve old completed files
  until replacement succeeds. Existing output is probed before being skipped.

## 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Homepage or malformed URL | Chinese validation error before download |
| Metadata API changed/404/non-JSON | Try public `videoInitialData` and verified episode links |
| HTTP 401/403 | Chinese permission error; no fabricated media source |
| Temporary server error | Bounded retry; respect Retry-After |
| Retry-After >30 seconds | Raise RetryLater; outer download loop must not immediately retry |
| Missing requested codec | Error; do not save a preview as a complete episode |
| FFmpeg exit 0 but missing-segment warning | Reject output |
| No video track or duration too short | Reject output |
| Cancelled | Reap FFmpeg and clean only this attempt's temporary directory |

## 5. Good / Base / Bad Cases

- Good: an episode URL containing tracking parameters downloads only that episode.
- Base: a series URL plus `--all` downloads each published episode, then skips valid
  existing outputs on another run.
- Bad: an HLS request loses a segment but FFmpeg exits 0; the final `.mp4` must not
  be published.

## 6. Tests Required

Use a local synthetic AES-128 HLS and local HTTP fixture to assert real decryption,
audio/video remuxing, missing segment rejection, cleanup, cancellation, access errors,
fallback parsing, and Retry-After behavior. GUI smoke checks must exercise actual
parse/select/download events. Per AGENTS.md, generated unit-test classes are removed
after completion; keep the outcomes in VERIFICATION.md and the task record.

## 7. Wrong vs Correct

Wrong: treat a zero FFmpeg return code as proof that all HLS segments were read.
Correct: combine return-code checks, segment-warning checks, and FFprobe validation
before publishing the temporary file.

Wrong: catch RetryLater in a generic DownloadError retry handler and immediately
obtain another signed address. Correct: propagate RetryLater before that handler.

Python uses colon/indentation blocks, not braces. Apply AGENTS.md's Chinese condition
and loop comments while preserving valid language syntax. All retained function
parameters and returns are annotated; business events and error messages are Chinese.
