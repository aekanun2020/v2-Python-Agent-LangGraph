PYTHON ?= python

.PHONY: test proof run-planner compare-lab8 compile

test:
	$(PYTHON) -m unittest -v tests.test_lab8_planner tests.test_lab8_comparison

proof:
	$(PYTHON) -m scripts.prove_planner_mcp

run-planner:
	$(PYTHON) labs/lab8_langgraph/agent_langgraph.py

compare-lab8:
	$(PYTHON) -m scripts.compare_lab8

compile:
	$(PYTHON) -m compileall -q labs scripts tests
