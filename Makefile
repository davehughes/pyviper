.PHONY: bootstrap test jenkins lint

bootstrap: env
	env/bin/pip install -r requirements.txt -r requirements-dev.txt

env:
	virtualenv env --distribute

test:
	env/bin/nosetests --with-coverage --cover-package=pyviper

jenkins: bootstrap
	env/bin/nosetests --with-coverage --cover-package=pyviper --cover-xml --cover-xml-file=coverage.xml

lint:
	env/bin/flake8 pyviper test

clean:
	find . -name '*.pyc' -delete
