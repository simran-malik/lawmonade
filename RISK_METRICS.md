# Case risk metrics by stage (brainstorm, Oct 2 2026)

Goal: for one case, show the top 1–2 things that put it at risk, given its current stage
(Clio `matter.stage`; Sapini = "Litigation"). Most signals are computable from Clio data,
but few are stored as a ready-made number.

Legend: **Direct** = a Clio field/record holds it · **Derived** = code computes it from Clio
records · **AI** = needs AI over free text (return a quote + confidence) · **Missing** = not in our Clio data.

## Top risk metrics per stage

| Stage | #1 risk metric | #2 risk metric | In Clio? |
|---|---|---|---|
| Intake / sign-up | Days left until statute of limitations (SOL) | Coverage unknown (no carrier / claim no. / policy limits) | #1 Direct: matter `statute_of_limitations` link (Sapini: "Limitations Date" task + calendar entry). #2 Direct: custom fields |
| Claims + treatment | Treatment gap: days since last treatment (>~30 days = warning) | Specials vs. coverage: medical bills near/above policy limits | #1 Derived: "Client treatment:" calendar entries + provider document dates + provider bill (expense) dates. #2 Direct: `Medical Specials To Date` vs `Policy Limits` |
| Records + bills | Age of oldest open records request (days overdue) | Providers with no records/bill on file | #1 Direct: pending "By medical provider:" tasks with due dates. #2 Derived: provider contacts vs docs in `04 Medical Records` / `05 Medical Bills and Liens` |
| Demand | Days since treatment ended with no demand sent | Unresolved lien amount | #1 AI + Missing: `Treatment Status` is free text (AI classify); "demand sent" not in data (needs custom field or doc-category convention). #2 Direct: lien field (app/liens.py) |
| Negotiation | Best offer vs. estimated value and limits | Days until a time-limited demand expires | Mostly Missing: offers live in notes/emails (AI extraction) or need custom fields. Clio has PI settlement features on some plans; none loaded in this account |
| Litigation | Overdue / upcoming hard deadlines (discovery, court) — missed = malpractice | Days since last client contact (cooperation risk) | Direct: task due dates + status, calendar entries, communication dates |
| Disbursement | Days from settlement to client paid | Liens not yet resolved | Partly: trust/bill data exists in Clio but the app doesn't pull it yet. Liens: Direct |

Cross-stage signals:
- **Days since any activity** (notes, communications, tasks) — Derived, easy.
- **Days in current stage** — Clio stores the stage but (as far as we know) not when it changed.
  Derive it from our dated snapshots in `data/matters/<id>/snapshots/`.

## What it flags on Sapini today (Litigation), from snapshot.json
- McCulloch Orthopaedic updated-records task: due 2026-08-25, still pending → **38 days overdue**.
- "Obtain updated employment and commission records": due 2026-09-26, pending → **6 days overdue**;
  the $214K wage-loss claim depends on it.
- Value vs coverage: `Estimated Case Value` $375K vs defendant $100K/person + $25K UM.
  Metro-North is self-insured, so the limit needs a human check → show as "verify", not a conclusion.
- No MMI after 3+ years; second (right shoulder) surgery date still unconfirmed → case can't be valued yet.
- `Liability Assessment` = "contested … neither investigated" while already in litigation (AI flag + quote).
- Last note 2026-09-15, last communication 2026-09-27.

## Build plan
1. `config/risks.yaml` (same pattern as `config/fields.yaml`): stage name aliases → top 2 metrics + thresholds
   (green/amber/red). Firms name stages differently; onboarding = edit YAML, no code change.
2. `app/risks.py`: date math in code, never the LLM (overdue days, SOL runway, treatment gap,
   days since contact). Use firm TIMEZONE / local date like the share code.
3. AI only for free-text fields (Treatment Status, Liability Assessment): return quote + confidence;
   code checks the quote exists in Clio text (same approach as app/liens.py); on timeout fall back to "needs review".
4. Add `risks` to `app/brief.py` output (and therefore GET /matters/{id}/brief); show red/amber/green cards
   with a "why" line + link to the Clio item, next to the money cards.
5. Read-only: building risks never writes to the DB.
6. Decided: demo only Litigation (the Sapini stage) plus the cross-stage signals; other stages added later in
   `config/risks.yaml` + one function each in `app/risks.py` (`STAGE_SIGNALS`).

## Built (Oct 2 2026)
- `config/risks.yaml`: `common` thresholds + `stages.litigation` (aliases, signals, thresholds).
- `app/risks.py: build(snap)` → `{stage, stage_key, set_up, note, signals, top}`; in `brief.build()` as `risks`
  (so also in GET /matters/{id}/brief), and shown above the money cards ("What could hurt this case").
- Litigation signals: `hard_deadlines` (any overdue task; a late court/discovery item is red at once; court items due
  within 7 days are amber), `client_contact` (newest email/call naming the client; Check if none does),
  `liability` (AI quote + confidence, checked against the field; else "needs review").
- Every stage: `days_since_activity`, `days_in_stage` (from dated snapshots; shows "N+ days" when every saved copy
  has the same stage, and never calls that lower bound green).
- Not yet: other stages; client-contact by sender/receiver (the loader doesn't fetch Clio's `senders`/`receivers`);
  risks in the digest email.
