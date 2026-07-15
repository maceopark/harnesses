# Bookmark Tags Greenfield

This directory implements the sealed `bookmark-tags-greenfield` Build Contract.
The command operates only on the adjacent `bookmarks.json` file.

```sh
python cli.py bookmark tag ID TAG
```

Every invocation prints one `StarterObservation.v1` JSON object to stdout. Run
the focused verification from the `harnesses` workspace root:

```sh
uv run --project measure-contract-drift --extra test pytest -q benchmark/bookmark-tags-greenfield/tests/test_bookmark_tags.py
```
