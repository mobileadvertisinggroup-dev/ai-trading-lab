# FINDING SD-GSHADOW — replacement shakedown (2026-08-27)

**Status: SURFACED BY THE SHAKEDOWN, ROOT-CAUSED MECHANICALLY, SUBMITTED
FOR ADJUDICATION. The defect record is preserved as emitted; no check
was weakened and the shakedown was not re-run.**

## Observation
G recorded 328 `fill_open` events; the G-shadow recorded 260. The
previous (defective, preserved) shakedown had exact fill-list equality,
so the strict check `g_opens == s_opens` fired as a constitutional
defect.

## Mechanical root cause (from the preserved event streams)
1. The shadow's 260 fills are a STRICT SUBSET of G's fills — every
   shadow fill matches a G fill at the same (t, symbol, side, qty).
2. The 68 G-only fills pair 1:1 with the shadow engine's 68 recorded
   `rejection` events, reason `max_positions`, at the SAME (t, symbol).
3. At every one of those rejections the shadow held exactly 10 open
   positions — the frozen engine/position cap.
4. Cause of the capacity gap: the shadow, BY DESIGN, receives G's entry
   submissions but only conventional exits (it exists to isolate the
   RL-management effect). The replacement Arm F policy (SB3 PPO seed 4)
   actively closes positions (290 executed closes on G), freeing G's
   slots early, while the shadow holds each position to its trailing or
   time exit. When both accounts were told to enter an 11th position, G
   had a free slot and the shadow did not.

## Why the strict check was previously green
The prior shakedown ran the defective zero-padded observation policy,
whose action stream never freed capacity ahead of the shadow, so the
fill lists coincided. Exact fill-list equality is therefore a property
of a NON-CLOSING management policy, not of correct wiring.

## Entry-submission identity (the intended constitutional property) HOLDS
Every entry G submitted was submitted identically to the shadow
(single `_submit` call, same qty, costs, caps); the only divergence
channel is the shadow's own account state at fill, and every divergent
fill is exactly accounted for by a shadow capacity rejection. RL management cannot
alter WHICH candidates G proposes at the symbol level: G's entry gating
uses the SHADOW's open-symbol set precisely so an RL close cannot
re-open a symbol for G that the shadow still holds. The capacity
(position-COUNT) divergence documented here is the one remaining
channel, and it is now fully quantified.

## Proposed refined property (for the adjudicator; NOT applied)
"G-shadow ENTRY-SUBMISSION identity: the shadow receives byte-identical
entry submissions; any fill divergence must be exactly matched, 1:1 at
the same (t, symbol), by a shadow-side capacity rejection with the
shadow at its position cap." This refined check passes on this run
(68/68, cap=10 at every rejection). Until adjudicated, the strict check
stays in force and its defect record stands.
