# QA review

An independent reviewer challenges each workpaper before the findings are graded. The goal is to find the conclusions that would not survive a careful reading.

Run this in a fresh context: a separate agent, a new session, or a different model from the one that audited the units. A reviewer who shares the auditor's context tends to repeat its mistakes.

## For each workpaper

1. **Re-open the evidence.** For at least two sampled items (all items if there are five or fewer), open the cited files yourself and confirm they show what the workpaper claims: the right incident, supplier, system, dates, times and values.
2. **Check the attributes against the requirements.** Do they test everything the control description promises and everything each requirement in `criteria` asks? A unit mapped to Art. 23(4) needs each deadline checked (early warning, notification, final report), not only that a report exists. A unit mapped to Art. 20(2) needs every member of the management body checked. A unit mapped to an Annex section needs the points that section lists, not only the Art. 21(2) heading.
3. **Recompute the deadlines.** For every reporting item, recompute the hours from awareness to each submission yourself, with time zones. Check that the awareness time is a recorded fact and not the time the ticket was classified.
4. **Look for missed deviations.** Compare dates and thresholds against the entity's documented information. Look for evidence dated outside the records period, approvals by the same person who made the change, an internal auditor reviewing their own area, incidents in the register classified significant but missing from the reporting population, and items marked `pass` with thin or unrelated evidence.
5. **Check `REQ-` units.** A requirement audited directly still needs documented information and a record of it working. A policy sentence alone is design evidence, not implementation evidence.
6. **Check the population test** (audits): was the population compared to an independent source, and does the comparison hold up?
7. **Check the wording.** Deviation descriptions must be factual and specific enough to print. Disagree when `statement`, a deviation description, `scope_limitation`, or `design.rationale` names anyone other than `management.name`, or contains an email address or a phone number. Those belong in `observations`. Disagree when report text is not in the engagement's `language`.
8. **Record the verdict:**

```bash
python scripts/nis2.py qa <engagement> <unit> --verdict agree --checked EV-0012 EV-0013 --by "<agent / model>"
python scripts/nis2.py qa <engagement> <unit> --verdict disagree --issue "Early warning for INC-2026-004 was 31 h after awareness but attribute A is marked pass" --checked EV-0044 --by "<agent / model>"
```

The command binds the verdict to the workpaper's current hash. If the workpaper changes after review, `validate --final` reports the review as stale and it must be reviewed again.

## After a disagreement

The workpaper goes back to auditing. The auditor fixes it, runs `validate`, and the reviewer reviews it again. A reviewer does not edit workpapers.
