FROM python:3.14-alpine

COPY requirements.txt ./
COPY summarize_test_results.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "/summarize_test_results.py"]
CMD ["--dir", "./test-artifacts"]
