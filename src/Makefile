test: compiler_tests

compiler_tests:
	python -m unittest compiler_tests.py -q

venv:
	virtualenv -p python3.7 ./venv && . venv/bin/activate && pip install -r requirements.txt
	@echo '***'
	@echo '*** You will need to activate the venv with: source ./venv/bin/activate'
	@echo '***'

clean:
	rm -rf venv


.PHONY: test compiler_tests venv clean
