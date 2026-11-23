# QA review

An independent reviewer challenges each workpaper before the findings are graded. The goal is to find the conclusions that would not survive a careful reading.

Run this in a fresh context: a separate agent, a new session, or a different model from the one that audited the units. A reviewer who shares the auditor's context tends to repeat its mistakes.

## For each workpaper

1. **Re-open the evidence.** For at least two sampled items (all items if there are five or fewer), open the cited files yourself and confirm they show what the workpaper claims: the right request, vendor, incident, dates and values.
2. **Check the attributes against the provisions.** Do they test everything the control description promises and everything each provision in `criteria` asks? A unit mapped to Art. 30(1) needs every field of Art. 30(1)(a) to (g) checked for every activity, not only that a record exists. A unit mapped to Art. 33(1) needs the time from awareness to notification checked, and the reasons for any delay. A unit mapped to Art. 28(3) needs the contract terms checked, not only a signature.
3. **Look for missed deviations.** Compare dates and deadlines against the Regulation and the organization's documented information: one month for requests (Art. 12(3)), 72 hours for notification (Art. 33(1)), the DPA signed before processing started, the DPIA completed before launch, sub-processor notice before the change. Look for evidence dated outside the records period, a breach assessed as "no risk" with no reasoning, a transfer with no mechanism, and items marked `pass` with thin or unrelated evidence.
4. **Check the roles.** Does the evidence show processing in a role the engagement leaves out? Does a unit test a processor obligation for a controller-only engagement, or the reverse?
5. **Check `REQ-` units.** An obligation audited directly still needs documented information and a record of it working. A policy sentence alone is design evidence, not implementation evidence. An obligation whose circumstances "do not arise" needs a record that shows it, not a statement.
6. **Check the population test** (audits of records over a period): was the population compared to an independent source, and does the comparison hold up?
7. **Check the wording.** Deviation descriptions must be factual and specific enough to print. Disagree when `statement`, a deviation description, `scope_limitation`, or `design.rationale` names anyone other than `management.name` (a data subject, an employee, a supplier's contact), or contains an email address or a phone number. Those belong in `observations`. Disagree when wording reads as legal advice or a statement about fines.
8. **Record the verdict:**

```bash
python scripts/gdpr.py qa <engagement> <unit> --verdict agree --checked EV-0012 EV-0013 --by "<agent / model>"
python scripts/gdpr.py qa <engagement> <unit> --verdict disagree --issue "DSR-009 answered after 45 days but attribute A is marked pass" --checked EV-0044 --by "<agent / model>"
```

The command binds the verdict to the workpaper's current hash. If the workpaper changes after review, `validate --final` reports the review as stale and it must be reviewed again.

## After a disagreement

The workpaper goes back to auditing. The auditor fixes it, runs `validate`, and the reviewer reviews it again. A reviewer does not edit workpapers.
