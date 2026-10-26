# Windows has no make: the commands below are the canonical form.
.PHONY: eval
eval:
	uv run python -m evals.report
