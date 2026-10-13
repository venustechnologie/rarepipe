"""Solvers. ``exact`` is the reference implementation the optimised path must agree with.

The optimised search in ``robust_policy`` earns its speed from memoisation, early exit and a
restricted action space. Each of those is a place a subtle bug can hide a reachable policy or
invent one, and the test for that is not inspection — it is a second implementation written to the
definition rather than to performance, and an assertion that the two never disagree.
"""
