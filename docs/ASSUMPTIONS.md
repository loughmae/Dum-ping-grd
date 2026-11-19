# Modelling assumptions (confirmed with the service)

## Confirmed rules
1. **Weekends are on-call only.** The hand-made rotas confirm this: full
   in-hours slot grids exist for Mon–Fri only; Saturday shows only the three
   Call rows (General Call, CT Call, Cath Lab Call) and Sunday shows none.
   The solver therefore treats Sat/Sun as on-call-only days.
2. **Grace, Allan, Ana, Maria, Katie were temporary staff** who no longer
   work here; they are excluded from the current pool (they remain visible in
   historical data).
3. **Irish bank holidays only.** The ingestion report flags these dates;
   bank holidays are covered by on-call only, matching observed practice
   (e.g. Mon 5 May 2025).

## Modelling approximations (to refine)
- **Shift hours**: early/late/wholeday slots count as 8h each; on-call
  carries no in-hours hours (a separate on-call allowance applies).
- **Person-day cap**: a person may work one wholeday slot, or one early +
  one late slot per day. The historical rota exceeds this on 13 person-days
  (3–5 slots); several are likely data artefacts (e.g. `Salim8-4*` counted
  in multiple rows) rather than real 40-hour days — needs coordinator
  confirmation.
- **On-call rest**: a person on call cannot work the same day. The
  historical rota breaks this 14 times in the sample week.
- **Pattern parsing**: free-text patterns are parsed to fixed working days
  or flexi-day counts (`3x 8-8` → any 3 days × 12h). Ambiguous single `T`
  days: double `T` → Tue+Thu; lone `T` with `W` → Thu, else Tue.
  Fortnight-alternating patterns (Salim) are modelled as 3 flexi days.
- **Weekly hours cap**: contracted hours +15% + 4h.
- **Bank staff** (Ashleen, Conor, Rebecca, Richael, Brandon) are excluded
  from solver assignments in the prototype; they remain listed.
- **Slot template** derives required headcount per weekday per canonical
  area (modality + shift block) as the rounded mean of observed staffing
  across Feb–May 2025; staffing-level values in the Area Reference are
  respected where they bind tighter.
- **Preferred area** gives a small solver bonus; no hard preferences yet.

## Historical rota audit findings (week of 2025-04-14)
- 0 skill mismatches — the Staff Qualifications matrix is consistent with
  practice.
- 8 pattern violations, 14 work+call same-day conflicts, 11 person-days
  with 3+ slots — inputs to discussions about which rules are truly hard.
