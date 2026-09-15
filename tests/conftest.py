import pytest

from powerbi_agent.analysis import profile
from powerbi_agent.planning import plan_model
from powerbi_agent.report import plan_report


@pytest.fixture
def sales():
    return profile("Sales", {"kind": "csv", "path": "C:/data/sales.csv", "delimiter": ","}, [
        {"OrderId": "001", "OrderDate": "2024-01-01", "ProductId": "P1", "ProductName": "Lamp", "Region": "North", "Revenue": "100", "Cost": "60", "Quantity": "2"},
        {"OrderId": "002", "OrderDate": "2025-02-01", "ProductId": "P2", "ProductName": "Book", "Region": "South", "Revenue": "200", "Cost": "90", "Quantity": "3"},
        {"OrderId": "003", "OrderDate": "2025-03-01", "ProductId": "P1", "ProductName": "Lamp", "Region": "North", "Revenue": None, "Cost": "20", "Quantity": "1"}])


@pytest.fixture
def model(sales):
    return plan_model([sales], "Analyze revenue, profit, products, regional trends, YoY growth and running totals")


@pytest.fixture
def report(model):
    return plan_report(model, "Analyze revenue, products, regions and detailed analysis")
