# QA review

An independent reviewer challenges each workpaper before the findings are graded. The goal is to find the conclusions that would not survive a careful reading by the client's security team.

Run this in a fresh context: a separate agent, a new session, or a different model from the one that assessed the units. A reviewer who shares the assessor's context tends to repeat its mistakes. The reviewer reads the bundle and the repository; it does not change them, and it does not call MCP servers or CLI tools again.

## For each workpaper

1. **Re-open the evidence.** Open the cited files yourself and confirm they show what the workpaper claims: the right table, bucket, file and line, setting, document, date.
2. **Check the attributes against the requirement.** Do they test everything the summary of the requirement in `assets/frameworks/app.yaml` asks? SEC-AC-01 needs every table the client can reach, not only the ones the code names; SEC-AC-02 needs read and write policies; SEC-CODE-01 needs every file shipped to the browser; DP-SUP-01 needs every service in the code scan and in `review/stack.yaml`; DP-SUP-03 needs a DPA for each sub-processor, not one.
3. **Look for missed weaknesses.** Compare the code scan findings, the advisor results and `review/stack.yaml` with the workpapers: a scan finding no workpaper mentions, a table in `tables` with RLS off, a bucket in `buckets` marked public, a sub-processor with no DPA export, a service-role key dismissed as "server code" that is in fact bundled for the browser.
4. **Check the evidence tier.** A `conforming` unit must rest on code, configuration or documents, not on answers. A unit that rests only on answers must be `inquiry-only`, with every procedure `inquiry`. An answer that admits a gap must have become a deviation, not `inquiry-only`.
5. **Check the role and optional scope.** Does the evidence show the developer still has production access while the role is `developer`? Does the app use file storage or AI while SEC-AC-06 or DP-AI are not in `include_optional`?
6. **Check the read-only rule.** Every capture in the bundle must be a read: MCP calls from a read-only, project-scoped server, CLI commands that only list or dump schema, no query that selects rows from application tables. Disagree when a capture shows otherwise, and raise it with the user.
7. **Check the wording.** Deviation descriptions must be factual and specific enough to print. Disagree when `statement`, a deviation description, `scope_limitation`, or `design.rationale` names anyone other than `management.name`, contains an email address or a phone number, or quotes a secret value (even partly). Those belong in `observations`. Disagree when wording reads as legal advice, a penetration test result, or a compliance verdict.
8. **Record the verdict:**

```bash
python scripts/app.py qa <engagement> <unit> --verdict agree --checked EV-0007 EV-0001 --by "<agent / model>"
python scripts/app.py qa <engagement> <unit> --verdict disagree --issue "storage.buckets shows id-documents public, but attribute A is marked pass" --checked EV-0009 --by "<agent / model>"
```

The command binds the verdict to the workpaper's current hash. If the workpaper changes after review, `validate --final` reports the review as stale and it must be reviewed again.

## After a disagreement

The workpaper goes back to assessment. The assessor fixes it, runs `validate`, and the reviewer reviews it again. A reviewer does not edit workpapers.
