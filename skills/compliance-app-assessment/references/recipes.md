# Stack detection and recipes

Stack knowledge is data. One recipe file per component in `assets/recipes/` says how to recognize the component and, for each piece of evidence, the ways to get it, best first. `detect` reads them; nothing about Supabase or Vercel is hard-coded in the engine.

## What detect does

`python scripts/app.py detect <dir> --repo <checkout>`:

1. **Scans the repository** (`scripts/common/codescan.py`). It reads git-tracked files only (skipping `node_modules`, build output and the like), runs nothing, and masks every secret it reports. It finds:
   - secrets: Supabase service-role keys (JWTs whose role is `service_role`), Stripe live keys, OpenAI and Anthropic keys, AWS access keys, Google API keys, private keys, GitHub tokens; committed `.env` files;
   - client code that refers to a service-role key; role checks in browser code (`client-side-authorization`); AI SDKs imported in browser code (`ai-sdk-in-client`);
   - third-party services the code uses (from `package.json` dependencies and known API hosts): AI, analytics, error tracking, email, payments, authentication, storage. Each is a sub-processor candidate;
   - the tables (`.from('...')`) and buckets (`.storage.from('...')`) the client code uses, for the RLS and storage checks;
   - dependencies and whether a lockfile pins them.
   Files under `supabase/functions/`, `api/`, `server/`, `netlify/functions/`, `app/api/`, `pages/api/`, migrations and scripts count as server code; everything else in a web app counts as client code.
2. **Matches recipes**: a recipe applies when any of its `detect` conditions matches (a dependency, a file glob, a text mention in README, `index.html`, `package.json` or the Vite config, or `always: true`).
3. **Records the scan** as evidence (`intake/NNNN-scan-...json`, tier `direct`), linked to the requirements of every recipe item that uses scan rules.
4. **Switches on optional requirements** a detected component `enables` (`include_optional` in `engagement.yaml`), and records `repo`.
5. **Writes** `review/stack.yaml` (components and why they were detected, sub-processor candidates, tables, buckets, scan findings) and `review/evidence-plan.md` (one section per recipe item in scope, with its methods in order, and at the end the requirements no recipe covers, with their catalog questions).

Run it again whenever the repository changes; each run adds a new scan capture and rewrites the plan.

## Recipe format

```yaml
component: supabase                  # unique id; also the file name
title: Supabase                      # printed in the plan
detect:                              # any match detects the component
  dependencies: ["@supabase/supabase-js"]
  files: ["supabase/config.toml", "supabase/migrations/*.sql"]   # globs relative to the repository root
  text: [supabase.co]                # mentioned in README.md, index.html, package.json or vite.config.*
  # always: true                     # always assessed (the app's own code)
subprocessor: {name: Supabase, service: "database, authentication, storage", dpa: "https://supabase.com/legal/dpa"}
enables: [SEC-AC-06]                 # optional requirement IDs that apply when the component is used
items:
  - id: supabase-rls                 # unique across recipes; passed to capture --recipe
    title: Row-level security status and policies per table
    requirements: [SEC-AC-01, SEC-AC-02]   # items whose requirements are all out of scope are left out of the plan
    scan_rules: [supabase-service-role-key] # codescan rules that are evidence for this item
    mcp: {server: supabase, tool: execute_sql, args: {query: "select ..."}, note: "..."}
    cli: {command: [supabase, db, dump, --schema-only, --linked]}
    export:
      en: "Supabase dashboard → Authentication → Policies: screenshot of every table ..."
      de: "Supabase-Dashboard → Authentication → Policies: Screenshot aller Tabellen ..."
```

The plan lists the methods in this order: scan, mcp, cli, export, then the catalog question of the item's first requirement as the answer route. Only the methods a recipe item defines appear.

## Adding a recipe for a new stack

1. Create `assets/recipes/<component>.yaml` in this skill (for example `firebase.yaml`, `clerk.yaml`, `stripe.yaml`).
2. **detect**: use what reliably identifies the component in a repository: an npm package, a config file (`firebase.json`, `.firebaserc`), a text mention. Prefer files and dependencies over text.
3. **subprocessor**: the provider's legal or product name, the service in a few words, and the URL of its standard DPA, if the component processes personal data. Leave it out for tools that do not (a linter).
4. **enables**: only optional requirement IDs (SEC-AC-06 for file storage, DP-AI-* for AI processing).
5. **items**: one per piece of evidence. For each:
   - `requirements`: catalog IDs from `assets/frameworks/app.yaml` that the evidence supports.
   - `mcp`: only a tool that reads, on a server that can be connected read-only and scoped to one project. If the server has no read-only mode, leave `mcp` out and say why in a comment, as the Lovable recipe does. SQL touches system catalogs and configuration tables only, never application rows.
   - `cli`: a command that only reads. Check it passes the read-only filter: `capture` refuses words such as `deploy`, `push`, `link`, `login`, `set`, `delete`, `exec`, `install`, and shell syntax. Use placeholders the tool resolves itself (`gh` resolves `{owner}/{repo}`), not values from a particular project.
   - `export`: the exact click path in the provider's console, in English and German, saying what to capture and that secret values must stay hidden.
   - `scan_rules`: only if a codescan rule produces evidence for the item. New rules go in `shared/lib/codescan.py` (a change to the shared engine, not to this skill).
6. Run `detect` on a repository that uses the component and read the plan. Then run the tests (`python -m unittest discover -s tests`).

## Shipped recipes

| Recipe | Detected by | Sub-processor | Enables | Items (requirements) |
|---|---|---|---|---|
| `web` | always | none | none | `web-secrets`: no privileged keys or secrets in code (SEC-CODE-01, SEC-CODE-02; scan). `web-client-authorization`: authorization not left to the browser (SEC-AC-03; scan). `web-third-parties`: services the code sends data to (DP-SUP-01, SEC-DATA-05; scan). `web-dependencies`: known vulnerabilities (SEC-CODE-03; `npm audit --json`, or export). `web-data-inventory`: personal data the app stores (DP-INV-01, DP-INV-02; schema export). |
| `supabase` | `@supabase/*` packages, `supabase/config.toml`, migrations | Supabase | SEC-AC-06 | `supabase-advisors`: security advisor (SEC-AC-01, SEC-AC-05, SEC-AUTH-03, SEC-AUTH-04; MCP `get_advisors`, export). `supabase-rls`: RLS status and policies per table (SEC-AC-01, SEC-AC-02; MCP `execute_sql` on `pg_class`/`pg_policies`, `supabase db dump --schema-only`, export). `supabase-security-definer`: functions with elevated rights (SEC-AC-05; MCP). `supabase-storage`: buckets and public flag (SEC-AC-06; MCP on `storage.buckets`, export). `supabase-project`: region and plan (SEC-DATA-01, SEC-OPS-07; MCP `get_project`, `supabase projects list`, export). `supabase-auth-settings`: email confirmation, passwords, MFA, providers, redirect URLs, sessions (SEC-AUTH-01, 02, 04, 06, 07; export). `supabase-backups`: backups and PITR (SEC-OPS-01, SEC-OPS-02; export). `supabase-team`: organization members and MFA (SEC-AC-07, SEC-AUTH-05; export). `supabase-edge-functions`: functions and caller verification (SEC-AC-04; MCP `list_edge_functions`). `supabase-logs`: logs available (SEC-OPS-03; MCP `get_logs`, without copying personal data). |
| `vercel` | `@vercel/*` packages, `vercel.json`, `.vercel/project.json` | Vercel | none | `vercel-env`: secrets in environment variables per environment (SEC-CODE-02, SEC-OPS-05; `vercel env ls`, export). `vercel-region-team`: function region and team access (SEC-DATA-01, SEC-AC-07, SEC-AUTH-05; export). |
| `netlify` | `netlify.toml`, `netlify/functions/*` | Netlify | none | `netlify-env-team`: environment variables, deploy contexts and team access (SEC-CODE-02, SEC-OPS-05, SEC-AC-07, SEC-AUTH-05; export). |
| `github` | `.github/` | GitHub | none | `github-branch-protection`: review on the production branch (SEC-OPS-06; `gh api .../rules/branches/main`, export). `github-vulnerability-alerts`: Dependabot and secret scanning (SEC-CODE-03, SEC-CODE-04, SEC-CODE-02; `gh api .../dependabot/alerts`, export). `github-access`: who can push (SEC-AC-07; `gh api .../collaborators`). |
| `lovable` | `lovable-tagger` package, mentions of lovable.dev | Lovable | DP-AI-08 | `lovable-backend-access`: which backend the builder can reach, and whether it is production (DP-AI-08, SEC-OPS-05; export). `lovable-workspace`: workspace members (SEC-AC-07; export). Lovable's MCP server acts with full account rights and has no read-only mode, so it is not used. |
| `ai` | AI SDK packages (`openai`, `@anthropic-ai/sdk`, `@google/genai`, `@ai-sdk/*`, `ai` ...) | (the providers, from the code scan) | DP-AI-01 to DP-AI-07 | `ai-calls`: where the app calls AI models, and from where (DP-AI-01, DP-AI-05; scan). `ai-provider-settings`: training opt-out and retention (DP-AI-02; export). `ai-dpa`: DPA and transfer mechanism with each provider (DP-AI-03; export). |

A Firebase, Netlify Blob, S3, Clerk or Stripe app is detected only through the code scan's service list until it has a recipe; plan evidence for it by hand from the catalog's `evidence` field, and consider adding the recipe.
