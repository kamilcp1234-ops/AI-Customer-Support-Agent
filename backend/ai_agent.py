
import logging
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from hindsight_client import Hindsight

# Import MySQL functions
from backend import database
from backend.database import get_or_create_customer, save_chat_history

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)
GROQ_TIMEOUT_SECONDS = 30
HINDSIGHT_TIMEOUT_SECONDS = 15
RESOLUTION_PREFERENCE_PATTERN = re.compile(
    r"APPROVED_RESOLUTION_PREFERENCE:\s*(Refund|Replacement|Voucher)\s*\n"
    r"SELECTED_AT:\s*([^\r\n]+)"
)
RESOLUTION_PREFERENCE_QUESTION_PATTERN = re.compile(
    r"\b(?:"
    r"preferred resolution|resolution preference|approved resolution preference|"
    r"what (?:is|was) my (?:latest|last|previous) resolution|"
    r"what (?:is|was) my (?:approved )?preference|what was my choice|"
    r"what resolution did i (?:choose|select|pick)|"
    r"which (?:resolution|option) did i (?:choose|select|pick)|"
    r"what did i (?:choose|select|pick)(?: last time| previously| for (?:my )?(?:resolution|complaint))?|"
    r"do you remember (?:my|what) (?:preferred resolution|resolution)"
    r")\b",
    re.IGNORECASE,
)


class AIServiceUnavailable(RuntimeError):
    """Raised when response generation cannot safely continue."""


# Connect to Groq
groq_client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
    timeout=GROQ_TIMEOUT_SECONDS,
    max_retries=0,
)


# Connect to Hindsight
memory_client = Hindsight(
    base_url=os.getenv("HINDSIGHT_BASE_URL"),
    api_key=os.getenv("HINDSIGHT_API_KEY"),
    timeout=HINDSIGHT_TIMEOUT_SECONDS,
    max_attempts=1,
)


# AI Customer Support Function
def get_ai_response(message, customer_id):

    # Create a separate memory bank for each customer
    bank_id = f"customer-{customer_id}"

    memories = []
    memory_available = True

    # Bank creation can report that a bank already exists; still try recall.
    try:
        memory_client.create_bank(
            bank_id=bank_id,
            name=f"Customer {customer_id}"
        )
    except Exception:
        logger.warning("Hindsight bank setup failed; attempting memory recall.")

    try:
        result = memory_client.recall(
            bank_id=bank_id,
            query=(
                f"Latest approved resolution preference and previous complaints, preferences and solutions "
                f"for customer {customer_id}. "
                f"Current message: {message}"
            )
        )
        memories = [memory.text for memory in result.results]
    except Exception:
        memory_available = False
        logger.warning("Hindsight recall failed; continuing without prior memory.")

    approved_resolution_preference = get_approved_resolution_preference(
        customer_id, recalled_memories=memories
    )

    memory_context = "\n".join(memories)

    if not memory_context:
        memory_context = "No previous customer memories found."

    preference_instruction = (
        f"The customer's latest approved resolution preference is {approved_resolution_preference}. "
        "Use it naturally when relevant. If asked what resolution they prefer or selected, "
        "state this preference explicitly. This is a remembered choice, not approval of a "
        "new complaint; never promise that a refund, replacement, or voucher has been issued."
        if approved_resolution_preference
        else "No previous approved resolution preference is available. If the customer asks "
        "about a previous approved preference, say exactly that. Do not infer or save one "
        "from what the customer says in this conversation."
    )

    if RESOLUTION_PREFERENCE_QUESTION_PATTERN.search(message):
        if approved_resolution_preference:
            answer = (
                "Your latest approved resolution preference is "
                f"{approved_resolution_preference}."
            )
        else:
            answer = "No previous approved resolution preference is available."
    else:
        # STEP 2: Generate AI response using Groq.
        try:
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful and professional customer support agent. "
                            "Use previous customer memories when relevant. "
                            "Never invent company policies, phone numbers, "
                            "email addresses, refund rules or delivery timelines. "
                            "Never claim that you have processed a refund, arranged "
                            "a replacement, created a ticket or shipped an order. "
                            "Do not promise actions that you cannot perform. "
                            "You do not have access to order records or shipment tracking. "
                            "Never claim that you can look up an order or check its status. "
                            "If information is unknown, clearly say so. "
                            "Ask the customer for relevant details when necessary. "
                            f"{preference_instruction}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Customer ID: {customer_id}\n\n"
                            f"Previous customer memories:\n{memory_context}\n\n"
                            f"Current message: {message}"
                        ),
                    },
                ],
                temperature=0.7,
            )
            answer = response.choices[0].message.content
            if not answer or not answer.strip():
                raise ValueError("Empty response")
        except Exception:
            raise AIServiceUnavailable from None

    if memory_available:
        try:
            memory_client.retain(
                bank_id=bank_id,
                content=(
                    f"Customer {customer_id} said: {message}\n"
                    f"Support agent replied: {answer}"
                ),
                context=f"Customer support conversation for {customer_id}"
            )
        except Exception:
            logger.warning("Hindsight retain failed; response was not remembered.")

    return answer


def retain_approved_resolution_preference(customer_id, resolution, selected_at=None):
    """Remember a choice only after the accepted complaint's SQL write succeeds."""
    if resolution not in {"Refund", "Replacement", "Voucher"}:
        return False

    bank_id = f"customer-{customer_id}"
    try:
        memory_client.create_bank(bank_id=bank_id, name=f"Customer {customer_id}")
    except Exception:
        # A bank can already exist; the retain attempt will report whether it
        # is actually available.
        pass

    if hasattr(selected_at, "isoformat"):
        selected_at = selected_at.isoformat()
    if not selected_at:
        selected_at = datetime.now(timezone.utc).isoformat()

    try:
        memory_client.retain(
            bank_id=bank_id,
            content=(
                f"APPROVED_RESOLUTION_PREFERENCE: {resolution}\n"
                f"SELECTED_AT: {selected_at}"
            ),
            context=f"Customer {customer_id} selected a resolution after an accepted complaint.",
        )
        return True
    except Exception:
        logger.warning("Hindsight resolution preference retain failed.")
        return False


def recall_approved_resolution_preference(customer_id):
    """Recall only explicit, marked post-acceptance resolution choices."""
    bank_id = f"customer-{customer_id}"
    try:
        memory_client.create_bank(bank_id=bank_id, name=f"Customer {customer_id}")
    except Exception:
        pass

    try:
        result = memory_client.recall(
            bank_id=bank_id,
            query=(
                "APPROVED_RESOLUTION_PREFERENCE selected after an accepted complaint; "
                "return the latest explicit preference marker if present."
            ),
        )
        return _extract_approved_resolution_preference(result.results)
    except Exception:
        logger.warning("Hindsight resolution preference recall failed.")
    return None


def get_approved_resolution_preference(customer_id, recalled_memories=None):
    """Return the latest DB-approved choice, using the customer's Hindsight bank as fallback."""
    memory_preference = (
        _extract_approved_resolution_preference(recalled_memories)
        if recalled_memories is not None
        else recall_approved_resolution_preference(customer_id)
    )
    try:
        result = database.get_latest_resolution_preference(customer_id)
        database_preference = result.get("resolution") if result else None
    except Exception:
        logger.warning("MySQL resolution preference lookup failed; using approved memory fallback.")
        database_preference = None
    return database_preference or memory_preference


def _extract_approved_resolution_preference(memories):
    candidates = []
    for memory in memories:
        text = memory if isinstance(memory, str) else getattr(memory, "text", "")
        text = text or ""
        # Only accept the complete canonical record we retained. A chat
        # transcript containing a similar phrase is not an approved choice.
        match = RESOLUTION_PREFERENCE_PATTERN.fullmatch(text.strip())
        if match:
            candidates.append((match.group(2), match.group(1)))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


# MAIN PROGRAM
if __name__ == "__main__":

    try:
        # STEP 4: Register or find customer in MySQL
        customer_name = "Rahul"

        customer_id = get_or_create_customer(customer_name)

        print("Customer registered successfully!")
        print("Customer ID:", customer_id)

        # STEP 5: Receive customer message
        message = input("\nCustomer: ")

        # STEP 6: Generate AI response
        answer = get_ai_response(message, customer_id)

        print("\nAI Support Agent:", answer)

        # STEP 7: Save conversation in MySQL
        save_chat_history(
            customer_id,
            message,
            answer
        )

        print("\nConversation saved in MySQL successfully!")

    except Exception as error:
        print("\nError:", error)

    finally:
        memory_client.close()
