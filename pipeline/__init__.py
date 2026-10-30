"""Code-driven question pipeline (docs/根因整改实施计划.md §3).

Code decides the steps: what the question asks, which calculations run, which facts may be
cited. The model writes the reading once from a fact sheet and may repair it once; the facts in
the answer are rendered by code from placeholders. Systems not yet moved here keep the agent loop.
"""
