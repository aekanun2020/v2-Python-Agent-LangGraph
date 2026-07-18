PYTHON ?= python

.PHONY: test proof run-planner compile

test:
	$(PYTHON) -m unittest -v tests.test_lab8_planner

proof:
	$(PYTHON) -m scripts.prove_planner_mcp

run-planner:
	$(PYTHON) labs/lab8_langgraph/agent_langgraph.py

compile:
	$(PYTHON) -m compileall -q labs scripts tests
