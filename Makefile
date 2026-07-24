PYTHON ?= python

.PHONY: test run-agent run-original compile

test:
	$(PYTHON) -m unittest -v tests.test_lab6_planner_runtime

run-agent:
	$(PYTHON) labs/lab6_todo/agent_planner.py

run-original:
	$(PYTHON) labs/lab6_todo/agent_todo.py

compile:
	$(PYTHON) -m py_compile labs/lab6_todo/agent_todo.py labs/lab6_todo/agent_planner.py
