# Glossary

Every term a reader of the other pages will hit, defined assuming no prior knowledge.

Each entry is tagged:

- **·** *biology* — standard scientific vocabulary, not specific to this project
- **·** *project* — **this project's own vocabulary.** If you use one of these with an outsider, you
  have to define it
- **·** *engineering* — general software term used in a specific way here

Alphabetical.

---

### A

**Actuator** · *project* — A specific physical means of moving a [control variable](#c). The
distinction from the variable itself is load-bearing: **when an actuator fails, the actuator closes
— the control variable does not**, unless the evidence speaks to the variable itself. Collapsing the
two closes biology that is still open.

**Admissibility gate** · *project* — A check that runs before any scientific conclusion is allowed:
is the sample's identity and provenance verified, and are precision, controls and required readouts
present. If either fails, no conclusion is permitted — and the conclusions that *would* have matched
are listed as `inadmissible_matches` rather than silently dropped.

**Aneuploidy** · *biology* — Having the wrong number of chromosomes. A normal human cell has 46; an
aneuploid cell has more or fewer.

**`all_of` node** · *project* — A node in the route map requiring **every** one of its members, not
any one of them. Its members are preconditions to *establish*, not waypoints with their own onward
path — which is why reachability is computed forwards rather than backwards.

**Artifact** · *project* — The versioned output of a pipeline stage: a JSON file with a schema
version, a content digest and provenance. Every artifact exists twice, as a `*.private.json` and a
sanitized sibling. Artifacts are **immutable**; re-running a stage produces a sibling run, never an
edit.

**Asserted only** · *project* — The weakest evidence level: a claim with no evidence reference behind
it. A causal edge with no citation **may only** be `asserted_only` — the code enforces it, so
retiring a citation determines the new support level mechanically rather than by judgement.

---

### B

**Biorientation** · *biology* — The correct state of an aligned chromosome: its two sister
chromatids attached to spindle microtubules from **opposite** poles, so they will be pulled apart
correctly.

**Bounded negative** · *project* — A negative result that names the universe it searched. "We
searched this corpus, of this size, with these queries, and found nothing" — **a statement about the
corpus, never about biology.** The project keeps three such states structurally apart:
`SEARCHED_EXTERNAL_UNIVERSE_EXHAUSTED`, `NOT_IN_LOCAL_CASE_CORPUS` and
`PHYSICALLY_INCOMPATIBLE_WITH_EVIDENCE`.

**Branch node** · *project* — A named unknown in the route map. It must enumerate **at least two**
admissible outcomes and continue from each, say why it is unresolved, and declare what kind of work
would answer it. **An unknown is never a dead end** — that is what branch nodes exist to prevent.

**Building block** · *project* — A typed transformation of biological state: *holds this variable at
this value, in this cell type, under these conditions.* Deliberately **never a drug name**, so pieces
compose without ever consulting a therapeutic indication.

**BubR1** · *biology* — The protein encoded by the gene *BUB1B*. A core component of the
[mitotic checkpoint](#m). It has at least two separable mitotic jobs — checkpoint signalling and
chromosome alignment — and, notably here, **its kinase domain is dispensable for both.**

**BUB1B** · *biology* — The gene encoding BubR1. Biallelic (both-copy) variants cause
[mosaic variegated aneuploidy](#m).

---

### C

**Campaign** · *project* — A **unit of work**, as against a branch which is a unit of ignorance. One
set of observations can settle several branches, so **a branch count overstates how many experiments
a route needs.** Do not read a campaign count as an experiment count.

**Checkpoint activation** · *biology* — The mitotic checkpoint doing its job: detecting an incorrectly
attached chromosome and **holding** the cell from dividing. Measured here by the response to a drug
that destroys the spindle.

**Checkpoint silencing** · *biology* — The **opposite** operation, and a different endpoint: once
every chromosome is correctly attached, the checkpoint must *switch off* so division can proceed. A
cell that cannot silence stalls. The project keeps activation and silencing rigidly separate, because
a protein can be competent at one and not the other.

**Chromosome alignment** · *biology* — Chromosomes being brought to the cell's equator, correctly
attached, before division. Also called congression.

**Claim** · *project* — A statement about the case, carrying a status (`SUPPORTED`,
`PARTIALLY_SUPPORTED`, `UNRESOLVED`, …), an [epistemic class](#e), a [scope](#s), and the evidence ids
behind it. A claim with no *establishing* evidence stays `UNRESOLVED` with a stated reason — it does
not become weakly supported.

**Clonal dynamics** · *biology* — The relative rates at which different cell populations grow and
die. Matters enormously here: **if an intervention kills aneuploid cells preferentially, every
fidelity readout improves while nothing has been corrected in any cell.**

**Cohesion** · *biology* — The molecular glue holding sister chromatids together until the moment
they should separate. Losing it early produces
[premature chromatid separation](#p).

**Compound heterozygous** · *biology* — Carrying **two different** damaging variants in the same gene,
one from each parent. Distinct from homozygous, where both copies carry the *same* variant.

**Confounder** · *biology* — Something that could produce your observation without the mechanism you
think is responsible. Here a reading counts as a clean discriminator only if **no uncontrolled
process could fake it**, and the system credits only experiments that measure the named confounders
too.

**Control variable** · *project* — A biological quantity you want to move — *attachment turnover*,
*poleward flux*, *cohesion protection*. Ten are declared for the live case. Contrast with
[actuator](#a).

**Corpus snapshot** · *project* — A frozen, versioned copy of retrieved literature. Retrieval is a
deliberate networked step that **writes** a snapshot; compilation **reads only** the snapshot. So
verdicts are reproducible months later and CI needs no network. **The corpus is the record.**

---

### D

**`DECLARED_SCIENTIFIC_FRONTIER`** · *project* — A terminal state meaning **nobody knows this** — a
genuinely open scientific question, as distinct from one we merely have not looked into. The live map
has exactly one, after three audits.

**Directness** · *project* — How closely a published experiment's variant relates to the case's own:
*exact*, *same position*, *within ten residues*, *same region*, *different region*. **Held only in
restricted fields**, because a nearby published variant plus a proximity grade would localise the
child's residue — the grade is identifying without containing an identifier.

**Disclosure boundary** · *project* — The code gate every outbound query passes. Nine pattern classes
are refused and it **fails closed**. A refusal is a bug to fix or a decision to escalate — never
something to work around.

---

### E

**Entry point** · *project* — An ancestor of a required outcome that nothing in the causal model
drives, so a transformation would have to act *there*. It names **where** a mechanism must act, never
**what** mechanism.

**Epistemic class** · *project* — What kind of knowledge a statement is: `observation`,
`external_evidence`, `derived_inference`, `unknown`. **There is deliberately no class for "a model
knows this"**, so anything an agent produces must cite held evidence or be recorded as an invalid
inference.

**Epistemic type** · *project* — The control compiler's finer-grained version, with 22 members.
`promote()` is the only legal way to change one, and it refuses to turn a derived result into an
observation without an external citation.

**Establishing vs indirect evidence** · *project* — Only certain evidence levels may **decide** a
claim's status. A computational predictor score or a protein-domain annotation is *visible* on a
claim but **cannot change its status** — it lands in `indirect_evidence`.

**Evidence family** · *project* — Several reports of **one original observation**, grouped so they are
counted once. Independence between families must be asserted by a named human — **two replies from
two institutions are not independent by default.**

**Exogenous variable** · *engineering* — A variable nothing in the model drives. In the live encoding
the three safety variables are declared exogenous on purpose, which is exactly why the compiler
**insists they be measured** rather than predicted.

---

### F

**Fails closed** · *engineering* — When uncertain, refuse. The disclosure guard is deliberately
over-broad for this reason: **a false refusal is cheaper than a false release.**

**Frontier** · *project* — (1) A justified leaf in the route map — one of eleven terminal states that
says **why** reasoning stops there. (2) In reachability, the minimal **sets** of unresolved branches
that would establish a node — sets rather than counts, because routes share experiments and summing
invents work that does not exist.

---

### G

**Governance blocked** · *project* — A terminal state meaning *not permitted, regardless of biology.*
Six leaves in the live map. One branch is blocked this way because no patient material is available
and none may be acquired — **it is not a biology problem and no experiment resolves it.**

**Grounding** · *project* — That a source **actually supports** the claim built on it. Distinct from
[retrieval](#r), which is only that a source was found. Three levels are tracked and never merged,
and only the third licenses a grounded verdict.

---

### H

**HGVS** · *biology* — The standard notation for describing a variant's position and change (for
example `NM_000000.0:c.…`, a synthetic placeholder). A refused pattern class at the disclosure
boundary.

**HPO** · *biology* — The Human Phenotype Ontology: standard coded terms for clinical features. An
HPO combination can identify a patient, so HPO identifiers are a refused pattern class.

---

### I

**Immutable artifact** · *engineering* — Written once, sealed with a checksum file, set read-only,
never edited. A run is staged in a hidden directory and only renamed into place once every file is
written, so **a crashed run never looks finished.**

**`INSUFFICIENT`** · *project* — The live case's current decision: the evidence does not settle
whether this child's specific allele retains function at restored abundance. **It is the correct
answer**, and the system reaching it rather than overclaiming is the result.

**Invalid inference** · *project* — A proposed statement that failed the grounding rules — no
citation, a citation outside the bundle, or a quote not found in the stored document. It is recorded
**with its reason and kept**, not silently dropped.

---

### K

**Kinase domain** · *biology* — The part of a protein that performs phosphorylation. In BubR1 it is
**dispensable** for both mitotic functions — so a substitution there matters because it
**destabilises the protein**, not because it removes catalysis.

**Kinetochore** · *biology* — The protein structure on each chromosome where spindle microtubules
attach. Where the mitotic checkpoint is monitored and enforced.

---

### L

**Latent variable hypothesis** · *project* — A candidate **single unobserved variable** that would
explain several otherwise unrelated neighbourhoods of the map. Held behind a firewall: it must be
non-traversable, may not also be a graph node, and **must predict something that was not used to
construct it** — otherwise it is only a new name for the pattern.

**Logical synthesizability** · *project* — A composition reaches the target **in the mathematics.**
Says nothing about whether it can be built. Kept rigidly apart from physical feasibility, and
**logical success never upgrades the physical verdict.**

---

### M

**Matched abundance** · *biology/project* — Expressing an altered protein at the **same level** as the
normal one, so that any remaining defect is a defect of *function* rather than of *amount*. The
central experimental idea in this case: without matching, a failure is uninterpretable because the
protein was simply too scarce.

**Missegregation** · *biology* — Chromosomes being distributed incorrectly during division —
the error that produces aneuploidy. The primary readout of the live case's functional target.

**Mitotic checkpoint** · *biology* — Also the spindle assembly checkpoint. The surveillance mechanism
that holds a dividing cell at metaphase until every chromosome is correctly attached. BubR1 is a core
component.

**Missense** · *biology* — A variant changing one amino acid to a different one. The protein is still
made, possibly with altered function or stability.

**Mosaic variegated aneuploidy (MVA)** · *biology* — A rare disorder in which cells carry varying
("variegated"), randomly distributed chromosome-number abnormalities, in only some cells
("mosaic"). Caused here by biallelic *BUB1B* variants.

**Motif hypothesis** · *project* — A structural pattern recurring across neighbourhoods of the map
that were authored independently. Like latent variables, held outside the graph and
**explicitly not traversable.**

**Mutation testing** · *engineering* — Deliberately breaking a check to confirm it goes red.
**A gate that passes on its first run proves nothing** — it might be checking the thing you meant, or
it might be inert.

---

### N

**`NO_CROSS_PREREQUISITE`** · *project* — Of the three bench questions: each can be **run and
interpreted** without knowing the others' outcomes. **A scheduling property, explicitly not
biological independence** — they may well share mechanism, and the project says so.

**Nonsense-mediated decay** · *biology* — A cellular quality-control process that destroys messenger
RNA carrying a premature stop codon, so a truncating variant often produces **less protein** rather
than a short one.

---

### P

**Poleward flux** · *biology* — The continuous movement of spindle microtubules toward the spindle
poles during mitosis. A physical property of the spindle, and the control variable FLUX01 targets.

**Precommitted interpretation matrix** · *project* — Written down **before the result exists**: for
each admissible outcome, what it licenses and — separately and explicitly — **what it does not
license.** This closes the gap that normally swallows a result: deciding after the fact what a number
meant.

**Premature chromatid separation (PCS)** · *biology* — Sister chromatids coming apart **before** they
should, because cohesion was lost early. A characteristic cytogenetic finding in MVA.

**Private artifact** · *project* — The `*.private.json` copy, holding everything the schema marks
restricted: variant identity, source sample labels, HPO term lists, directness grades. Never leaves
the controlled environment, and gitignored.

**Provenance** · *engineering* — The record of exactly what produced an artifact: software version,
git commit and dirty flag, Python version, platform, library versions. Plus, scientifically, where
every statement came from.

---

### R

**Required function** · *project* — What must become true for the target state to hold, expressed as
a position in the causal model rather than as an intervention. The output of inverting the target.

**Restricted field** · *project* — A schema field that exists **only** in the private artifact. A
field declared `restricted()` is cleared recursively to produce the sanitized copy — **schema-driven,
not list-driven**, so adding a sensitive field means tagging it and there is no second list to
forget.

**Retrieval** · *project* — Finding a source. **Not** the same as [grounding](#g), and the project
keeps them in separate fields, code paths and verdicts, because conflating them is how an evidence
base rots.

**Residual function** · *project* — Whether the altered protein still works **once its abundance is
restored.** The live case's open question, and the thing that cannot be answered from class-level
evidence.

**Result class** · *project* — The single explicit headline of a compilation, from a closed
vocabulary. Each ships with a fixed sentence of meaning so that, for example, "uncontrollable" cannot
be read as "biologically impossible". **A report validator refuses any headline its own contents do
not support** — no result by prose.

**Route class** · *project* — How a candidate control works: repair, stabilization, compensation,
bypass, suppression, replacement, rewiring. **Repair is one family, not the privileged one**, and the
code cannot prefer it.

---

### S

**Sanitized artifact** · *project* — The publishable copy, produced by clearing every restricted
field. **It is not anonymous**, and the sanitizer says so itself: internal aliases remain and it
still describes one real individual's case structure.

**Scope** · *project* — What a claim is **about**: `exact_variant`, `same_residue`, `nearby_variant`,
`variant_class`, `gene_level`, `disease_level`. **Scope cannot be borrowed** — evidence about other
variants in the same domain is `variant_class` and may not stand in for an exact-variant claim.

**Semantic digest** · *engineering* — A hash of what an artifact **says**, excluding how long it took
to say it. Two identical runs must produce the same digest, which is what makes drift detectable.

**Selective loss** · *biology* — Aneuploid cells dying off, which lowers the aneuploid fraction
without correcting anything. **Fewer errors in a dying population is selective loss, not rescue** —
which is why viability, cell death and division rate are required readouts rather than optional ones.

**`SYNTHETIC_ROUTE_FEASIBILITY_UNKNOWN`** · *project* — A **successful** output, and the most
misread term in the project. It means: the route works under every evidence-compatible model, and
what is missing is a way to **build** it, named per component.

---

### T

**Target region** · *project* — The state the cell must achieve, as a conjunction of conditions. The
route to it is **solved for**, not specified — which is why restoring a protein's abundance is kept
*out* of the target definition and treated as a candidate route.

**Terminal state** · *project* — Why a leaf in the route map is a leaf. Eleven closed values, so that
*reached the target*, *unsafe*, *not permitted*, *ruled out by evidence*, *searched and found
nothing* and *nobody knows* are six different claims and the strongest has to earn it. **A terminal
may never mean "we stopped reasoning."**

**Transfer gap** · *project* — Whether evidence was measured in the **system this case needs**. Kept
separate from whether the evidence supports the mechanism at all — folding the two together would
make every step fail for the same blanket reason and hide which step actually breaks.

**Truncating variant** · *biology* — A variant introducing a premature stop, so the protein is cut
short or — via [nonsense-mediated decay](#n) — largely not made.

**Turnover** · *biology* — The rate at which a protein is degraded and replaced. Faster turnover means
less protein at steady state, even when the gene is transcribed normally. **The mechanism of low
abundance in the live case is turnover, not transcription.**

---

### U

**`UNEXPANDED_FRONTIER`** · *project* — A leaf acknowledging *we have not expanded this yet, and we
are saying so.* **The live map has zero.** An earlier version had thirteen leaves that looked like
frontiers and were really unexpanded branches — expanding them produced an entire strategy family
nobody had noticed was missing.

**Unknown function** · *project* — An explicitly unresolved causal relationship. A relationship is
either a **total** lookup table or **explicitly unknown** — there is deliberately no third state
where it is merely absent, because an absent relationship is indistinguishable from a forgotten one.

---

### V

**Validity gate** · *project* — A condition under which an experiment is interpretable **at all**,
including which published results your hands must reproduce first. **A null without validated
engagement is not a null.**

**Variant class** · *project* — A group of variants treated together, typically by protein domain.
The live case's central tension lives here: **103 establishing records at variant-class level, 0 at
exact-allele level.**

---

### W

**Weakest-link cap** · *project* — A prediction inherits the **weakest** evidence on its path, so
adding more assertions can never raise a verdict. This is the opposite of multiplying plausible
numbers together: it keeps the specific link where the reasoning breaks **visible in the output**
instead of averaging it away.

---

## Where to go next

- **The science these terms describe** —
  [`08-for-clinicians-and-researchers.md`](./08-for-clinicians-and-researchers.md).
- **The epistemic vocabulary in depth** —
  [`05-evidence-discipline.md`](./05-evidence-discipline.md).
- **The map vocabulary in depth** — [`06-route-map.md`](./06-route-map.md).
- **The compiler vocabulary in depth** — [`04-control-compiler.md`](./04-control-compiler.md).
- **The authoritative source for any term** — each subsystem's `model.py` or `kinds.py`. The enums
  are closed on purpose, and they are the clearest available statement of what that subsystem
  believes.

---

> Retrieval is not grounding. A bounded negative is a statement about the corpus, not about biology.
> Feasibility unknown is a successful output.
