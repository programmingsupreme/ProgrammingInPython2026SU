import requests
import json


def fetch_data(endpoint):
    url = f"https://api.spacexdata.com/v3/{endpoint}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data from {endpoint}")
        return []


def print_data(data):
    print(json.dumps(data, indent=4))


if __name__ == "__main__":
    endpoint = input("Enter the SpaceX API endpoint (e.g., ships, launches, rockets): ")
    data = fetch_data(endpoint)
    print_data(data)
