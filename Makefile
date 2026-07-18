PYTHON ?= python
HR_CHALLENGE ?= skills_project_risk

.PHONY: test proof run-planner compare-lab8 compare-lab8-hr validate-hr-challenges compile

test:
	$(PYTHON) -m unittest -v tests.test_lab8_planner tests.test_lab8_comparison tests.test_hr_challenges

proof:
	$(PYTHON) -m scripts.prove_planner_mcp

run-planner:
	$(PYTHON) labs/lab8_langgraph/agent_langgraph.py

compare-lab8:
	$(PYTHON) -m scripts.compare_lab8

validate-hr-challenges:
	$(PYTHON) -m scripts.validate_hr_challenges

compare-lab8-hr:
	$(PYTHON) -m scripts.compare_lab8_hr --challenge $(HR_CHALLENGE)

compile:
	$(PYTHON) -m compileall -q labs scripts tests
