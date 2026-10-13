"""Benchmark harness for the policy engine: episodes, an exact oracle, splits and metrics.

Separate from ``policy/`` on purpose. The engine is the thing under test and must not be able to
see the test; this package imports the engine, never the reverse, and ``policy/`` keeps its own
boundary test proving it imports nothing outside itself.

The harness is being built before the symbolic solver, deliberately, so that errors in the
episodes, the schemas and the metrics surface now rather than after a deeper solver exists. The
cost of that ordering is that real episodes must stay inside the region where the exhaustive solver
is exact — today a horizon of three. That is a restriction on the *episodes*, not a softening of
the oracle: an episode whose oracle could not be computed exactly is not admitted, and
``oracle.py`` refuses rather than records a guess.

    build → freeze → run arms → score

Nothing here runs a language model. The arms come later; what is built first is the part that
decides whether an answer is right, because a benchmark whose scorer is unverified measures
nothing.
"""
