FROM python:3.14-alpine

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENTRYPOINT [ "python", "/summarize_test_results.py"]
CMD ["--dir", "./test-artifacts"]
