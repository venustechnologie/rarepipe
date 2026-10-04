"""Biological State Control Compiler.

    Reason with agents. Prove with code.

    Agents may propose biological states, mechanisms, alternative routes, models, controls,
    actuators and experiments. Deterministic mathematical code must evaluate constraints,
    reachability, consistency, observability, provenance and safety wherever those concepts have
    formal semantics. Missing biological knowledge must remain an explicit unknown. The system must
    never manufacture quantitative semantics merely to complete a computation.

    We do not ask only what an intervention will do.
    We specify what biology must do, then solve for how to make it happen.

The forward question — given this intervention, what happens? — is replaced by the inverse one:
given the state we have and the state we want, which biological variables would have to be
controlled to move from one to the other without ever passing through a forbidden state?

This phase implements the finite-state formalism, because every measurement in the first case is
categorical or ordinal. Other formalisms (interval, ODE, stochastic) are named in the model contract
and refused by the compiler until an adapter to an established solver is added; the compiler does
not contain a numerical integrator and is not meant to.
"""
