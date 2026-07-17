# Owner World Model: Bookmark Tagging

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Bookmarks have stable IDs and an ordered list of tags.
- The requested operation adds one tag to one existing bookmark.
- Bookmark title and URL are unrelated data and must be preserved.

## Vocabulary and decision posture

- Tag identity is exact string identity; case folding and whitespace normalization are not authorized.
- Adding an existing tag is a successful no-op, not a duplicate append.
- An unknown bookmark is an error and must not create a bookmark.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"bookmarks","items":[{"item_id":"target-only","owner_statement":"Adding a tag changes only the identified bookmark's tags and preserves its ID, title, URL, and every other bookmark.","materiality":"critical","forbidden_outcomes":["Changing bookmark metadata","Tagging a different bookmark"]},{"item_id":"duplicate-noop","owner_statement":"If the exact tag already exists on the bookmark, the operation succeeds as a no-op and does not append a duplicate.","materiality":"critical","forbidden_outcomes":["Duplicate tag entries"]},{"item_id":"unknown-id-no-write","owner_statement":"An unknown bookmark ID fails without changing bookmarks.json.","materiality":"material","forbidden_outcomes":["Implicit bookmark creation"]}],"probes":[]}
```
