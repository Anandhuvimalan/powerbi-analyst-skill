"""Deterministic fictitious retail data with known totals and seasonality."""
import csv
import datetime as dt
import random
from pathlib import Path

def main():
    rng = random.Random(41)
    products = [("P01", "Desk Lamp", "Home", 48, 27), ("P02", "Travel Pack", "Travel", 92, 51),
                ("P03", "Wireless Speaker", "Electronics", 125, 77), ("P04", "Water Bottle", "Outdoor", 28, 12)]
    regions = ["North", "South", "East", "West"]
    path = Path(__file__).resolve().parents[1] / "examples" / "sales.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["OrderId", "OrderDate", "CustomerId", "CustomerSegment", "ProductId", "ProductName", "ProductCategory", "Region", "Quantity", "Revenue", "Cost"])
        for i in range(1200):
            product = products[rng.randrange(4)]
            customer = rng.randrange(1, 81)
            date = dt.date(2024, 1, 1) + dt.timedelta(days=rng.randrange(730))
            units = rng.randrange(1, 9)
            writer.writerow([f"O{i+1:05}", date.isoformat(), f"C{customer:03}", "Business" if customer % 3 == 0 else "Consumer",
                product[0], product[1], product[2], regions[customer % 4], units, units * product[3], units * product[4]])
    print(path)

if __name__ == "__main__":
    main()
