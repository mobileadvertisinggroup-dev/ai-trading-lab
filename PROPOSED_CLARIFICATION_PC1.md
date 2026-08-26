# PROPOSED PROTOCOL CLARIFICATION PC-1 — awaiting explicit user approval

Status: **ADOPTED as FINAL-1.2.1** (explicit user approval 2026-08-25: "PC-1 is approved by us", after independent review). Originally: Required by the independent review
verdict §4 (2026-08-25). Real ingestion is prohibited until the user
explicitly approves or rejects this clarification. If approved it becomes a
versioned amendment recorded in the spec lineage (FINAL-1.2 → FINAL-1.2.1);
if rejected, an alternative ingestion design must be agreed before any
ingestion.

## The mismatch being adjudicated

- **Spec wording** (FINAL-1.2 §2 phase list; §9.1–9.2; R53): "the holdout
  range is mechanically established by the frozen Phase-1 partition rule
  before ingestion"; "No plaintext holdout-period data may exist in the
  project's readable raw lake"; "Raw holdout-period data must pass directly
  through a non-interactive sealing process into encrypted storage at
  ingestion."
- **Implementation reality**: the concrete holdout *dates* are a function
  of data availability (the eligible-interval rule needs the availability
  calendars), so the acquisition pipeline must see the complete source
  stream — in ephemeral runner staging — before it can compute the
  boundary and seal the holdout side. The RULE is frozen before ingestion;
  the resulting DATES are computed during the sealing run.

Neither silently reinterpreting the spec nor pretending the dates are
knowable without data is acceptable; hence this explicit clarification.

## Proposed amendment text (the minimal diff)

Insert into SPEC §9, after item 3 ("Mechanical pass-through inside the
sealing utility is permitted; display is not."):

> **3a. Source acquisition vs. project ingestion.** A non-interactive
> sealing process MAY acquire the complete public source history into
> isolated, ephemeral runner storage solely to: (i) validate data quality
> mechanically; (ii) determine the eligible continuous interval; (iii)
> compute the binding 60/20/20 boundary; (iv) divide the source stream
> into pre-holdout and holdout records; (v) encrypt the holdout records.
> "Project ingestion" means admission into the ordinary readable project
> data lake; no holdout-period row may enter that lake. Acquisition
> staging MUST be: inaccessible to model training, validation, dashboard,
> and ordinary diagnostic code; free of any display of holdout values,
> rows, summaries, or outcomes; limited to metadata-only logs; never
> committed to Git; never uploaded as an ordinary Actions artifact; never
> cached between runs; destroyed immediately after successful sealing or
> on failure, with the run FAILING if destruction cannot be verified.
> Only pre-holdout data enters the readable lake; holdout data goes
> directly from isolated acquisition staging into the encrypted seal.

Corresponding one-line touch-ups (no semantic change beyond the above):
- §2 phase list item 3: "the holdout range is mechanically established by
  the frozen Phase-1 partition rule **applied during the sealing process,
  before any project ingestion**".
- R53 reading: the protocol foundation (the RULES) is frozen before
  ingestion; the DATES those rules produce are computed inside the sealing
  process per §9.3a.

## Scientific consequences (honest statement)

1. **No change to the experiment's information structure.** The boundary
   remains a pure mechanical function of the frozen rules plus the source
   stream; no human or model choice enters between acquisition and
   sealing. Nothing the models can ever read changes: the readable lake
   still contains zero holdout-period rows.
2. **The builder-knowledge caveat is unchanged.** SPEC §8 already states
   the holdout is public history and the builder cannot be proven
   ignorant of it; PC-1 neither widens nor narrows that caveat. The
   sealing process is code, runs non-interactively, and logs metadata
   only, so no holdout VALUES reach the agent, logs, or repository.
3. **The alternative is worse.** Fixing calendar dates before seeing data
   availability would either (a) hard-code dates chosen by a human — a
   favorable-appearance risk §7 exists to prevent — or (b) risk a holdout
   window with unusable data quality. Mechanical post-acquisition
   computation is the design most faithful to §7's "mechanically, never by
   favorable appearance".
4. **Residual risk named.** During the sealing run, plaintext
   holdout-period bytes exist transiently in runner memory/temp storage.
   This is exactly the §9.3 "mechanical pass-through" allowance, now with
   explicit protections and verified destruction.

## Implementation status

The ingestion code and workflow have been hardened to the §3a protections
(see HOLDOUT_POLICY.md §4a and the updated `lab-ingest` workflow):
runner-temp staging outside the checkout, metadata-only logging, no
caching, no artifact upload of staging, and a destruction step whose
verification failure fails the run. These protections are binding for any
future ingestion regardless of PC-1's outcome; PC-1 itself changes only
the spec's wording to match.

**Decision requested from the user:** APPROVE PC-1 (adopting the amendment
text above as FINAL-1.2.1) or REJECT with direction.
