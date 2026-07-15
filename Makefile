.PHONY: build verify install install-shutdown user-test

PYTHON ?= python3

build:
	$(PYTHON) scripts/automation.py build

verify:
	$(PYTHON) scripts/automation.py verify

install:
	$(PYTHON) scripts/automation.py install

install-shutdown:
	$(PYTHON) scripts/automation.py install --shutdown

user-test:
	bash scripts/user_test.sh
