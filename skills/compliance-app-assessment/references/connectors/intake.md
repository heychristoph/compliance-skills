# Intake connector

Adds everything in the engagement's `intake/` folder to the bundle: the code scan `detect` recorded, MCP tool responses, read-only CLI output, the exports and screenshots the user provided, and the user's answers. Every app assessment uses it; it is the only source when there is no records folder.

## Configure

```yaml
source:
  connector: intake
  options: {}                 # optional path: a different folder that contains intake/ (default: the engagement folder)
```

`app.py init <dir> ... --connector intake`. With a records folder as well: `--connector intake --connector records --option records.path=<records folder>`.

## What it reads

| intake/ | Bundle artifact |
|---|---|
| `NNNN-scan-*.json` (written by `detect`) | evidence, `obtained: direct`, linked to the requirements of the recipe items that use scan rules |
| `NNNN-mcp-*` | evidence, `obtained: captured`, with the server, tool and arguments in `capture` |
| `NNNN-cli-*` | evidence, `obtained: captured`, with the command, exit code and working directory in `capture` |
| `NNNN-export-*` | evidence, `obtained: client`, with the original file name |
| `NNNN-answer-*.md` | evidence, `obtained: inquiry`, with the question as asked |

Each artifact keeps the title, the requirement and control IDs, the recipe item and the capture time from the `.meta.json` sidecar, and is dated by the capture.

## Rules that matter here

- **Order.** Run `detect` first: it writes the scan into `intake/`. Then capture, then `ingest`. After any new capture, `ingest --replace`; the old bundle is kept aside as `bundle.replaced-<timestamp>`, and artifact IDs can change, so run `validate` afterwards and fix workpapers that cite old IDs.
- **Captures are never edited or deleted.** If a capture is wrong (the wrong project, a screenshot with a secret in it), tell the user. A capture with a secret must not stay in the record: ask the user to remove that file and its `.meta.json` themselves, then capture a clean one. Do not delete it yourself.
- **Unknown requirement IDs** are dropped from the artifact with a warning. Fix the ID by capturing again.
- **No control matrix.** With intake alone, ingest warns that no source provided a control matrix, and every requirement in scope is assessed directly as a `REQ-` unit. That is expected.
- **Answers are inquiry.** An artifact from `answer` never makes a unit conforming on its own; see [../control-testing.md](../control-testing.md).
