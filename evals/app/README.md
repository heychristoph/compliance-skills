# App assessment evals

A synthetic Lovable-built Supabase app ("Kestrel Bookings", physiotherapy bookings with
treatment notes and AI summaries) with planted weaknesses, plus the recorded results of
the Supabase MCP calls, the user's exports and answers that an agent would gather.

```bash
python evals/app/make_fixture.py
python evals/app/run.py --case processor --agent oracle
python evals/app/run.py --case developer --agent oracle --language de
python evals/app/run.py --case processor --agent 'claude -p --permission-mode bypassPermissions {prompt}'
```

**Cases**

- `processor`: the supplier runs production. All 60 requirements apply once detect switches on the AI and storage items.
- `developer`: the client runs production. Processor-only items (backups, breach notice, sub-processor DPAs) are out of scope and listed with the reason.

**Planted weaknesses**

| ID | Requirement | Grade | What | Found through |
|---|---|---|---|---|
| D1 | SEC-CODE-01 | major | service-role key in `src/lib/supabase.ts` | code scan (direct) |
| D2 | SEC-AC-01 | major | RLS off on `treatment_notes` | Supabase MCP `get_advisors` and RLS query (captured) |
| D3 | SEC-AC-06 | major | public bucket with ID documents | Supabase MCP storage query (captured) |
| D4 | DP-AI-05 | minor | OpenAI called from the browser | code scan (direct) |
| D5 | SEC-AUTH-04 | minor | admin MFA not enforced | auth settings export (client) |
| D6 | SEC-AC-03 | minor | admin access decided in the browser | code scan (direct) |
| D7 | DP-SUP-03 | major | no DPA with OpenAI (processor only) | contracts export (client) |

**Answers only.** SEC-OPS-02 (restore test), DP-LIFE-02 (erasure) and DP-INC-02 (breach notice) are supported only by answers. They must come out `inquiry-only`, which the report shows as "not verified".

**Graders** check the defects and grades, plus:
- detect found the stack, the code scan rules and the sub-processors
- every evidence tier is present
- the evidence-strength summary is in Section I
- the role-based scope is applied
- the annexes and fixes list are written
