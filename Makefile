PYTHON ?= python3

.PHONY: context check test package clean example

context:
	$(PYTHON) scripts/gen-context.py

check:
	$(PYTHON) scripts/check-all.py

test:
	$(PYTHON) -m unittest discover -s tests -v

package:
	$(PYTHON) scripts/package-release.py --output dist

example:
	$(PYTHON) scripts/init-project.py --name "Example Project" --id example-project --output build/example-project --force

clean:
	rm -rf build dist __pycache__ tests/__pycache__ scripts/__pycache__
