Episode Index and Transcription Status
=====================================

Overview
--------

podx persists per-subscription episode status so the UI can quickly mark
episodes as already transcribed and avoid redundant work. The index is a small
JSON file stored alongside each subscription’s data directory.

Location
--------

- Base directory per subscription: `root_dir/{key}/` where `{key}` is the
  human-readable subscription key from `FeedsMetaService` (`slug--shortid`).
- Index file: `root_dir/{key}/episodes_index.json`.

Entry Schema
------------

Each entry records one episode that has been transcribed:

{
  "episode_id": "guid:abcd..." | "encl:https://…/audio.mp3" | "h:p37n…",
  "title": "Episode title",
  "published_date": "2025-08-20",
  "guid": "…" | null,
  "enclosure_url": "…" | null,
  "status": "transcribed" | "failed",
  "episode_dir": "/…/root_dir/{key}/episodes/…",
  "vtt_path": "/…/transcript.vtt",
  "txt_path": "/…/transcript.txt",
  "created_at": "2025-08-21T12:34:56",
  "updated_at": "2025-08-21T12:35:00",
  "error": "short failure description" | null,
  "summary_path": "/…/summary.txt" | null,
  "summary_updated_at": "2025-08-21T13:00:00" | null
}

Identity Rules
--------------

- Prefer RSS `guid` as the episode identity.
- Fallback to the enclosure audio URL if available.
- Otherwise, hash a tuple of (published date + normalized title).

Usage
-----

- The UI (`PodcastView`) looks up entries by GUID/enclosure (or the fallback) to
  set the “transcribed” indicator for each feed item.
- `IngestionService` writes a new entry after a successful transcription when it
  has the subscription context (feed URL/title) to resolve the subscription key.
  On failures it records a `failed` entry with a short `error` message.

 Timestamps and Summary Files
 -----
 
 - `created_at` marks when the episode was first recorded in the index (first
   successful transcription or first failure).
 - `updated_at` reflects the last time the transcript metadata changed
   (typically when a new transcript was generated or the status flipped to
   `failed`). The UI’s Transcript tab shows this timestamp in its header.
 - `summary_path` and `summary_updated_at` are reserved for episode summaries.
   The Summary tab currently displays a placeholder; when summaries are added,
   the summary file path and last generation time will be persisted here without
   touching transcript timestamps.

 Notes
 -----

 - The index is additive; entries are updated in place when regeneration
   happens. Additional states such as `downloaded` can be added when needed.
 - The identity fallback (published+title) is best-effort and may be ambiguous
   if feeds change titles retroactively. GUID/enclosure provide the most
   reliable mapping and are preferred whenever available.
