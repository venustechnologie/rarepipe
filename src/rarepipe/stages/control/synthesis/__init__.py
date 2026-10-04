"""Synthetic Biological Control Architecture Compiler.

The control compiler answers: given candidate controls, do they reach the desired state?
This layer answers the inverse: given the desired state, what architectures could produce it?

    desired state -> required functions -> architectures -> building blocks -> actuators

Nothing here assumes the answer must repair the altered gene, restore the original protein, follow
a natural pathway, use a single intervention, or correct every cell. Repair is one family among
several, and the compiler is not allowed to prefer it because it is the obvious one.

Two separations carry the whole design:

* **Reason with agents. Prove with code.** Agents imagine architectures, name building blocks,
  find compensations and attack weak routes. Only deterministic code decides reachability, safety,
  observability, robustness and whether anything was synthesized at all.
* **Logical synthesizability is not physical feasibility.** A composition that reaches the target
  in the mathematics is a result; it is not a proposal to do anything, and the report is built so
  that one can never be read as the other.

This phase implements the finite-state formalism. It does not solve differential equations, does
not recommend treatments, and produces no intervention list before a control objective exists.
"""
from __future__ import annotations

SYNTHESIS_PRINCIPLE = (
    "Do not ask biology only what will happen if we perturb it. Ask what biology must do for the "
    "desired state to exist, then synthesize a way to make those conditions true."
)
