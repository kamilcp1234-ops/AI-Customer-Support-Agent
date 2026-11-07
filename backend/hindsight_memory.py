
import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

# Load environment variables
load_dotenv()

# Connect to Hindsight Cloud
client = Hindsight(
    base_url=os.getenv("HINDSIGHT_BASE_URL"),
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

# Memory bank for our customer support agent
BANK_ID = "customer-support-demo"

# Create the memory bank
client.create_bank(
    bank_id=BANK_ID,
    name="Customer Support Agent"
)

print("Hindsight connected successfully!")

# Store customer information
client.retain(
    bank_id=BANK_ID,
    content=(
        "Customer Rahul reported that his order arrived damaged. "
        "He prefers a replacement instead of a refund."
    ),
    context="Customer support conversation"
)

print("Customer memory stored successfully!")

# Retrieve customer information
result = client.recall(
    bank_id=BANK_ID,
    query="What happened to Rahul's order and what resolution does he prefer?"
)

print("\nRecalled customer memories:")

for memory in result.results:
    print(memory.text)

# Close connection
client.close()
