PYTHON ?= python3

.PHONY: context check test package clean example

context:
	$(PYTHON) .agents/bootstrap/scripts/gen-context.py

check:
	$(PYTHON) .agents/bootstrap/scripts/check-all.py

test:
	$(PYTHON) -m unittest discover -s tests -v

package:
	$(PYTHON) .agents/bootstrap/scripts/package-release.py --output dist

example:
	$(PYTHON) .agents/bootstrap/scripts/init-project.py --name "Example Project" --id example-project --output build/example-project --force

clean:
	rm -rf build dist __pycache__ tests/__pycache__ .agents/bootstrap/scripts/__pycache__ .agents/acp/lib/__pycache__
