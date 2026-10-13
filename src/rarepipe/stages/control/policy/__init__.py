"""Robust contingent policy search over an AND/OR decision graph under hard safety constraints.

**This package is domain-neutral and must stay that way.** Nothing here may import a case, a map,
a biological vocabulary or an adapter. The entry point takes a graph, a knowledge state, a target, a
constraint set and a horizon, and it would solve a logistics problem with the same code. Case
specifics — which terminal kinds are unsafe, which capabilities are available, which campaigns are
declared, which outcomes are invalid runs rather than results — arrive as arguments.

The direction of dependency is the whole point, and ``tests/test_policy_boundary.py`` enforces it:
an adapter may import this package; this package may not import an adapter. That is what lets the
solver be extracted later without rewriting the algorithm.

    from rarepipe.stages.control.policy import solve_policy
    result = solve_policy(graph, state, target="GOAL", constraints=Constraints(), horizon=6)
"""
from rarepipe.stages.control.policy.actions import (Action, ActionSpace, Arm, DECLARED_CAMPAIGN,
                                                    UNDECLARED_CAMPAIGN, UNDECLARED_RESOLVER,
                                                    build_action_space)
from rarepipe.stages.control.policy.certificates import AdversaryWitness, minimal_closing_combinations
from rarepipe.stages.control.policy.graph import (ALL_OF, BLOCKED, BRANCH, COMPONENT_DISCOVERY,
                                                  FRONTIER, GOAL, GraphError, IMPOSSIBLE,
                                                  MEASUREMENT, Edge, Node, PolicyGraph, STATE,
                                                  TERMINAL, UNSAFE)
from rarepipe.stages.control.policy.ranking import (PROGRESS_COMPONENTS, Candidate, ProgressVector,
                                                    component_names)
from rarepipe.stages.control.policy.reachability import (Frontier, blocking_outcomes,
                                                         conditionally_reachable, dominators,
                                                         frontier)
from rarepipe.stages.control.policy.robust_policy import (BUDGET, Constraints, FALSE, HORIZON,
                                                          NOT_ESTABLISHED, PolicyNode, PolicyResult,
                                                          TRUE, Verdict, solve_policy)
from rarepipe.stages.control.policy.state import (ActuatorStatus, AVAILABLE, CLOSED_INEFFECTIVE,
                                                  CLOSED_NO_ENGAGEMENT, CLOSED_UNSAFE,
                                                  KnowledgeState, Observation, seed_actuators)
from rarepipe.stages.control.policy.update import (goal_closed, goal_reached, unsafe_routes, update)

__all__ = [
    "ALL_OF", "AVAILABLE", "Action", "ActionSpace", "ActuatorStatus", "AdversaryWitness", "Arm",
    "BLOCKED", "BRANCH", "BUDGET", "CLOSED_INEFFECTIVE", "CLOSED_NO_ENGAGEMENT", "CLOSED_UNSAFE",
    "COMPONENT_DISCOVERY", "Candidate", "Constraints", "DECLARED_CAMPAIGN", "Edge", "FALSE",
    "FRONTIER", "Frontier", "GOAL", "GraphError", "HORIZON", "IMPOSSIBLE", "KnowledgeState",
    "MEASUREMENT", "NOT_ESTABLISHED", "Node", "Observation", "PROGRESS_COMPONENTS", "PolicyGraph",
    "PolicyNode", "PolicyResult", "ProgressVector", "STATE", "TERMINAL", "TRUE",
    "UNDECLARED_CAMPAIGN", "UNDECLARED_RESOLVER", "UNSAFE", "Verdict", "blocking_outcomes",
    "build_action_space", "component_names", "conditionally_reachable", "dominators", "frontier",
    "goal_closed", "goal_reached", "minimal_closing_combinations", "seed_actuators",
    "solve_policy", "unsafe_routes", "update",
]
