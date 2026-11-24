# Implementation research

The target exposes ordinary JSON metadata at `GET /api/videos/{id}` and ordinary
playback data at `POST /api/videos/{id}/episodes/{ep}/playback`, body `{}`.
Playback fields include `id`, `ep`, `manifest_method=GET`, `streams.main`, optional
`streams.hevc`, and dynamic CDN auth metadata. The main tested stream uses ordinary
AES-128 MPEG-TS HLS, while the HEVC sample uses fragmented MP4 HLS.

GitHub project Alos21750/UAV-Downloader, commit
3cb9f07af934373a90ef1de822b5696efb98623c, contains a Huangguo adapter under Apache-2.0.
Its retry-after and public HTML initial-data/episode parsing logic was adapted
to stdlib HTMLParser and user-supplied mirrors. Full provenance is recorded in
THIRD_PARTY_NOTICES.md; the upstream license was saved verbatim.

yt-dlp FFmpegFD was inspected for headers/stream-copy conventions; its code was
not copied. N_m3u8DL-RE was considered as a generic HLS tool reference.

An important regression discovered during implementation: FFmpeg may skip a missing
HLS segment and still return 0. The downloader therefore also detects segment-read
warnings and rejects output whose duration fails the expected-duration check.
Long Retry-After requirements propagate as RetryLater and cannot be retried by the
outer per-episode loop.
