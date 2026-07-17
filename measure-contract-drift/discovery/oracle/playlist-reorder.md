# Owner World Model: Playlist Reorder

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Track IDs are stable and the order of the `tracks` array is the playlist order.
- Playlist name and visibility are not mutation targets.
- POSITION is a human-facing one-based destination.

## Vocabulary and decision posture

- Moving removes the identified track and inserts it at the requested final position.
- Position must be between 1 and the playlist length, inclusive.
- Moving a track to its current position is a successful no-op.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"playlist-reorder","items":[{"item_id":"one-based-final-position","owner_statement":"POSITION is one-based and names the track's final position after the move.","materiality":"critical","forbidden_outcomes":["Off-by-one placement"]},{"item_id":"permutation-only","owner_statement":"A valid move changes only track order and preserves every track object, playlist name, visibility, and track count.","materiality":"critical","forbidden_outcomes":["Duplicating or dropping a track","Changing playlist metadata"]},{"item_id":"invalid-no-write","owner_statement":"An unknown track or out-of-range or non-integer position fails without changing playlist.json; moving to the current position is a successful no-op.","materiality":"material","forbidden_outcomes":["Clamping an invalid position"]}],"probes":[]}
```
