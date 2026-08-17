install:
	python -m pip install -r requirements.txt

test:
	pytest -q

run:
	uvicorn app.main:app --reload
