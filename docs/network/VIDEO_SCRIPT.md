# Three-minute video script — MVA_001

**Target: ~3:00 at a calm pace (~460 words). Timings are cues, not hard cuts.**
No screen recording is required. Speak to camera or over two or three still slides.

---

### 0:00 — What this is about

A child has mosaic variegated aneuploidy. Their cells get chromosome counts wrong when they
divide — some end up with extra chromosomes, some with too few. The gene involved is BUB1B, which
makes a protein called BubR1 that helps hold a dividing cell back until it is ready to separate.

Our question for Track 2 was whether an existing medicine could improve that underlying biology.

### 0:25 — What we found in Track 1

We analysed the controlled data locally, with network access blocked throughout. Our top-ranked
prediction matched the clinically confirmed variant pair, at rank one. We froze the prediction file
before querying the evaluator, so there is a record of what we predicted and when.

### 0:50 — The hypothesis, and what is wrong with it

One candidate is nicotinic acid — niacin — an approved medicine for lipid disorders. The reasoning
is that it can raise NAD, which the enzyme SIRT2 uses, and published work links SIRT2 to greater
stability of BubR1.

We are not going to oversell that. The experiment supporting the SIRT2 link used a different NAD
precursor. Raising a protein's abundance helps only if the protein can still do its job, and
whether this child's variant leaves it able to is unresolved in our review. We also kept a related
experiment that did not show the hoped-for effect.

### 1:25 — What we built, and why it matters more than the hypothesis

So we built the thing that outlives any one hypothesis.

Before any experiment runs, our system writes down what each possible result would mean. If the
cells divide better, that is recorded as one thing. If they divide better but more of them die,
that is a different thing, and the system will hold the conclusion rather than call it a success.
If a result is uninterpretable, it stays uninterpretable — it cannot quietly become a yes.

We can then run the whole decision forward under different assumed worlds. A world where the
protein still works. A world where it does not. A world where the measurement is unreliable. The
team sees, in advance, which results would actually change what they do and which would leave them
exactly where they started.

### 2:10 — Who could answer the open questions

From public work only, we produced a short list of research groups and services able to speak to
each open question, and for each one, the precise question and the smallest useful reply — an
existing result, a referral, or simply "we cannot help."

Nothing has been sent. Our software cannot send. That is a decision for the clinician and the
family, and we hand them the list and the drafts.

### 2:40 — What we are claiming

We have not established a treatment, and no child has been given anything. We have mapped one
hypothesis, shown where it is weak, written down in advance what would count as an answer, and
named who could help find out.
