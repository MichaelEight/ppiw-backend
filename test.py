import time
import requests

url = "https://ai.darkstarlight.eu/getPrediction"
payload = {"points": [[0.0] * 6 for _ in range(64)]}
headers = {"Content-Type": "application/json"}

times = []

print("Sending 10 requests...")
for i in range(1, 11):
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, headers=headers)
        end_time = time.time()
        
        duration = end_time - start_time
        times.append(duration)
        print(f"Request {i}: status {response.status_code} | time: {duration:.4f} s")
    except requests.exceptions.RequestException as e:
        print(f"Request {i} failed: {e}")

if times:
    avg_time = sum(times) / len(times)
    print("-" * 40)
    print(f"Average response time: {avg_time:.4f} s")