Feed Metadata Cache and Subscription Keys
=========================================

Overview
--------

To render the subscriptions list quickly without repeatedly fetching RSS feeds,
podx caches channel‑level metadata (title, description, icon) in a local JSON
file and identifies each subscription with a stable, human‑readable key.

Files
-----

- `root_dir/feeds_meta.json`: Stores an array of objects like:

  {
    "key": "99-percent-invisible--p37n2w5q",
    "feed_url": "https://example.com/feed.xml",
    "title": "99% Invisible",
    "description": "…",
    "publisher": "Radiotopia",
    "icon_url": "https://…/art.jpg",
    "etag": "W/\"abcd\"",
    "last_modified": "Tue, 27 Aug 2024 19:00:00 GMT",
    "last_fetch": "2024-08-27T21:13:00.000000"
  }

Key Generation
--------------

- The per‑subscription key is `slug--shortid`:
  - `slug`: Slugified podcast title (ASCII, lowercase, hyphen‑separated).
  - `shortid`: First 8 chars of a base32‑encoded SHA‑256 digest of a
    canonicalized feed URL (scheme/host lowercased, fragment removed, query
    params sorted with common tracking params dropped).
- Keys are deterministic and stable across renames; the digest depends only on
  the feed URL. In the unlikely event of a collision with a different URL, a
  numeric suffix (`-2`, `-3`, …) is appended.

Usage
-----

- The UI uses `FeedsMetaService` to:
  - Generate and persist keys the first time a subscription is seen.
  - Read cached descriptions immediately when rendering the list.
  - Refresh stale/missing metadata in the background (default TTL: 24h) using
    conditional requests (`If-None-Match`/`If-Modified-Since`). Rows update as
    fresh data arrives.
- The key doubles as a filesystem‑safe directory name for storing per‑podcast
  data under `root_dir/{key}/…`. Existing features that write podcast data can
  use `FeedsMetaService.podcast_dir(name, feed_url)` to get the canonical path.

Notes
-----

- Descriptions are stored as received; the UI renders a single-line elided
  snippet for performance.
- The cache is resilient to network failures; missing fields simply remain
  `null` until a successful refresh.

Retention policy (on unsubscribe)
---------------------------------

By default, feed metadata is retained in `feeds_meta.json` even after a
subscription is removed. This is intentional:

- Pros:
  - Faster re-subscribe: the UI can show cached title/description immediately.
  - Efficient conditional requests: preserved `ETag`/`Last-Modified` enable
    cheap 304 checks instead of full downloads.
  - Minimal disk impact: entries are small JSON objects.
- Cons:
  - File can accumulate entries for past subscriptions over time.
  - Some users may prefer strict cleanup for privacy/tidiness.

Potential alternatives (not enabled by default):

- Eager cleanup: remove a feed’s metadata immediately on unsubscribe (and
  optionally delete its per-podcast directory).
- Lazy garbage collection: periodically prune metadata not referenced by any
  subscription and older than a chosen retention window (e.g., 60 days).

If you want a different behavior, consider adding a config flag such as
`remove_on_unsubscribe` (bool) or `retain_orphans_days` (int) and implementing a
small cleanup pass at startup.
