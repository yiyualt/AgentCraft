from ddgs import DDGS

query = "mlflow是什么"

with DDGS() as ddgs:
    results = list(ddgs.text(
        query,
        max_results=5,
        region="cn-zh",
        safesearch="off",
    ))

print(results)