# Verity — how to explain it (prep sheet)

Status note: written while the build was in progress. Anything marked (VERIFY) must be checked on the running app before you say it on stage.

## 1. One sentence (the USP, agreed by all five council lenses)
"Verity doesn't hand you a verdict. When new evidence lands, it re-opens only the findings that depended on it, shows the cited before-and-after, and voids any human approval that is now out of date. It does this live, on the jury's own unseen case."

Say "we found no public product that does this", never "first" or "nobody has". The methods are established; the combination, running live on unseen input, is what is new.

## 2. The problem (30 seconds)
A claim arrives as scattered evidence: photos, the claimant's account, the policy, a repair estimate. When they disagree (rear-impact story, front-damage photo) the lazy answer is "fraud". The honest answer is: inconsistency -> possible explanations -> what evidence would tell them apart -> a recommendation for a human. Evidence also keeps arriving, and today analysts redo work or, worse, act on stale analysis.
Stakeholders: the claims adjuster (needs a defensible file), the reviewer/manager (signs off), the claimant (needs a fair, faster outcome), compliance (needs an audit trail).

## 3. What the product does (the demo story, about 3 minutes)
1. Create a case, drop the policy PDF, the claimant statement, a damage photo and the repair estimate. Each file is read and turned into facts, each fact tagged: observed, reported, computed, inferred or human.
2. Hypothesis Board: competing explanations are laid out, always including a benign one. The board ranks them by fewest contradictions (no probabilities, no fraud score). A benign explanation sits next to the worrying ones.
3. Next-evidence request: the system asks for the single most useful document, says which explanations it would separate and what is at stake in rupees, and locks a prediction of what each outcome would mean.
4. Settlement: exact decimal arithmetic on the supplied policy terms. If a term is missing it refuses to give a number and lists what it needs.
5. A reviewer approves. The approval is sealed to that exact revision (hash on the PDF).
6. THE MOMENT: a juror hands over a new document. Only the findings that depended on it go stale (hatched), re-resolve with a cited before/after diff, the request ranking updates and the locked prediction is scored, and the earlier approval flips to VOID.
7. Proof Lab: quality gates run live on that same upload.

## 4. How it works (architecture, in the TCS order: Input -> AI -> Tools -> Data -> Decisions -> Human -> Output)
- Input: any file or typed statement via one drop bar.
- AI: a "reader" model that has no tools turns documents into structured JSON (it treats embedded instructions as content). A separate "planner" proposes hypotheses, findings and requests from that JSON only.
- Tools (closed registry, arguments validated, every call logged on a visible tape): read policy clause, check estimate totals, claim-history lookup (synthetic), weather lookup (free Open-Meteo, if available), create evidence request (idempotent).
- Data/knowledge: PostgreSQL 16 (bundled, runs without admin), originals stored privately with SHA-256, every revision stored as one document, hash-chained audit log.
- Decisions: deterministic code does the money, staleness, ranking and receipt checks. The model only extracts and proposes.
- Human control: the AI never denies, never labels fraud, never releases payment. Approval is a reviewer action; role is chosen from a delegation table by rupees at stake (adjuster up to 50,000; senior up to 2,00,000; committee above). The reviewer name is a typed label, not authentication, and we say so.
- Output: version-bound PDF, DRAFT watermark unless approved.

## 5. The innovations and where they come from (how to credit them)
| Feature | Plain-language pitch | Inspiration |
|---|---|---|
| Living Case File | Every finding remembers its evidence; new evidence re-opens only dependants | Truth maintenance systems (Doyle 1979), Git's hashed versions, code-review diffs |
| Hypothesis Board | Competing explanations, ranked by contradictions, next evidence ranked by how well it separates them | Heuer's Analysis of Competing Hypotheses, clinical differential diagnosis, value of information, pre-registration |
| Trust layer | Every number and quote is checked against the source page; instructions hidden in documents are quarantined | Dual-LLM pattern (Willison), CaMeL (Google DeepMind), OWASP LLM01, Chain-of-Verification |
| Proof Lab | Quality checks run live on any upload; labelled scenarios; name-swap fairness test | promptfoo / Pydantic Evals style harnesses, counterfactual fairness (Kusner et al.) |
| Vehicle blueprint | Three rings: where the story, the photo and the estimate say the damage is | SAE J224 clock-position damage zones |
Honest framing: these are established ideas; we combined them for claims and made each a live moment.

## 6. How it scores against TCS's rubric
- Capabilities (need 5 of 7, aim for all): Reason (multi-source board), Plan (plan strip), Act (tool tape), Verify (receipts, gates), Adapt (the moment), Human control (approval voiding), Evaluate (Proof Lab).
- Challenge asks: document understanding, image reasoning, policy interpretation, evidence consistency, incident reconstruction, anomaly detection, missing-evidence identification, alternative explanations, settlement recommendation.
- Success measures: reasoning quality, policy interpretation, traceability, consistency detection, fair handling of uncertainty.
- Slides (max 5): problem and stakeholders; architecture; live prototype; evidence/evaluation/responsible AI; adaptation and business impact.

## 7. Honest limits (say them before they are asked)
- All evidence is synthetic and labelled. Evaluation scenarios are team-written, so they show regression and consistency checks, not field accuracy.
- Policy terms are a synthetic Indian motor policy. Only plastic/rubber 50%, fibre glass 30% and glass nil depreciation were found in insurer wordings; everything else is labelled synthetic and editable.
- No real authentication; reviewer is a typed label.
- Free Gemini tier: some models were overloaded when we tested (gemini-3.8-flash timed out; 3.6-flash, 3.5-flash, 3-flash-preview answered), so the app fails over between models and shows a degraded mode if all fail.
- Business impact: no invented savings. Say what a pilot would measure: review time per case, rework avoided, time to resolve an evidence request.
- The Gemini key was shared in chat: rotate it after the event and delete backend/.env before sharing the folder.

## 8. Likely questions
- "Is this just an LLM wrapper?" No: the model only extracts and proposes; staleness, ranking, receipts, money and approval voiding are deterministic code you can inspect.
- "Why not output a fraud score?" Because the evidence shows inconsistency, not intent; an invented score would be unexplainable and unfair. We give explanations and the next evidence instead.
- "What if the model hallucinates a quote?" Every quote and amount must be found in the source text after normalisation; failures show as UNVERIFIED and are excluded from the money.
- "What if the jury's document contains instructions?" The reader has no tools and its output is schema-bound; instruction-like text is listed as an embedded instruction and ignored.
- "What if the AI is down?" Hashing, EXIF, PDF text/OCR, arithmetic, receipts and review still work; AI sections say unavailable and the system asks for what it needs.
- "How does it scale or integrate?" Case state is one versioned document; tools are a closed registry that can point at a policy admin or claims system; a pilot would plug those in.
