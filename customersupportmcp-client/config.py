import os
from dotenv import load_dotenv

load_dotenv()

MCP_SERVER_PATH: str = os.getenv(
    "MCP_SERVER_PATH",
    r"c:\projects\dambar projects\customersupportmcp\main.py",
)
DEFAULT_CUSTOMER_ID: str = os.getenv("DEFAULT_CUSTOMER_ID", "CUST-001")
