PYTHON ?= python
HR_CHALLENGE ?= skills_project_risk

.PHONY: test proof proof-pure-planner run-pure-planner compare-lab6-hr compare-lab6-hr-adversarial compare-observation-policy-hr compare-semantic-observation-hr run-planner compare-lab8 compare-lab8-hr validate-hr-challenges compile

test:
	$(PYTHON) -m unittest -v tests.test_lab6_planner_runtime tests.test_observation_policy tests.test_hr_analytical_contract tests.test_lab8_planner tests.test_lab8_comparison tests.test_hr_challenges

proof:
	$(PYTHON) -m scripts.prove_planner_mcp

proof-pure-planner:
	$(PYTHON) -m scripts.prove_pure_python_planner

run-pure-planner:
	$(PYTHON) labs/lab6_todo/agent_planner.py

compare-lab6-hr:
	$(PYTHON) -m scripts.compare_lab6_hr --challenge $(HR_CHALLENGE)

compare-lab6-hr-adversarial:
	$(PYTHON) -m scripts.compare_lab6_hr --challenge $(HR_CHALLENGE) --adversarial

compare-observation-policy-hr:
	$(PYTHON) -m scripts.compare_observation_policy_hr

compare-semantic-observation-hr:
	$(PYTHON) -m scripts.compare_semantic_observation_hr

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
