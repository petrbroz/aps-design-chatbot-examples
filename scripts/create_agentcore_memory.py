import sys
from botocore.exceptions import ClientError
from bedrock_agentcore.memory import MemoryClient


def create_agentcore_memory(memory_name: str) -> str:
    """Create an AgentCore memory resource with short-term memory."""
    memory_client = MemoryClient()
    try:
        memory = memory_client.create_memory_and_wait(
            name=memory_name,
            strategies=[],
            description="Short-term memory for design agent",
            event_expiry_days=7,
        )
        memory_id = memory["id"]
        return memory_id
    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationException" and "already exists" in str(e):
            # If memory already exists, retrieve its ID
            memories = memory_client.list_memories()
            memory_id = next((m["id"] for m in memories if m["id"].startswith(memory_name)), None)
            return memory_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("    python create_agentcore_memory.py <memory_name>")
        sys.exit(1)
    memory_name = sys.argv[1]
    memory_id = create_agentcore_memory(memory_name)
    print(f"AgentCore Memory ID: {memory_id}")
