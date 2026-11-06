import httpx

with httpx.Client(timeout=5.0) as client:
    response = client.get(
        "http://127.0.0.1:9000/v1/parcels",
        params={"offset": 0, "limit": 5},
    )

    response.raise_for_status()
    data = response.json()

    for parcel in data["items"]:
        print(parcel["id"], parcel["name"])