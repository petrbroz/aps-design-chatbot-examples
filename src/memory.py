import logging
from strands.hooks import AgentInitializedEvent, HookProvider, HookRegistry, MessageAddedEvent
from bedrock_agentcore.memory import MemoryClient
from botocore.exceptions import ClientError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


client = MemoryClient()
memory_name = "DesignAgentMemory"
memory_id = "DesignAgentMemory-JPhjwm3tB2"

# try:
#     # Create memory resource without strategies (thus only access to short-term memory)
#     memory = client.create_memory_and_wait(
#         name=memory_name,
#         strategies=[],  # No strategies for short-term memory
#         description="Short-term memory for design agent",
#         event_expiry_days=7, # Retention period for short-term memory. This can be upto 365 days.
#     )
#     memory_id = memory["id"]
#     logger.info(f"Created memory: {memory_id}")
# except ClientError as e:
#     logger.info(f"ClientError: {e}")
#     if e.response["Error"]["Code"] == "ValidationException" and "already exists" in str(e):
#         # If memory already exists, retrieve its ID
#         memories = client.list_memories()
#         memory_id = next((m["id"] for m in memories if m["id"].startswith(memory_name)), None)
#         logger.info(f"Memory already exists. Using existing memory ID: {memory_id}")
# except Exception as e:
#     # Show any errors during memory creation
#     logger.error(f"Error: {e}")
#     import traceback
#     traceback.print_exc()
#     # Cleanup on error - delete the memory if it was partially created
#     if memory_id:
#         try:
#             client.delete_memory_and_wait(memory_id=memory_id)
#             logger.info(f"Cleaned up memory: {memory_id}")
#         except Exception as cleanup_error:
#             logger.error(f"Failed to clean up memory: {cleanup_error}")


class MemoryHookProvider(HookProvider):
    def __init__(self, memory_client: MemoryClient, memory_id: str):
        self.memory_client = memory_client
        self.memory_id = memory_id

    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Load recent conversation history when agent starts"""
        try:
            # Get session info from agent state
            actor_id = event.agent.state.get("actor_id")
            session_id = event.agent.state.get("session_id")

            if not actor_id or not session_id:
                logger.warning("Missing actor_id or session_id in agent state")
                return

            # Load the last 16 conversation turns from memory
            recent_turns = self.memory_client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                k=16
            )

            if recent_turns:
                # Format conversation history for context
                context_messages = []
                for turn in recent_turns:
                    for message in turn:
                        role = message["role"]
                        content = message["content"]["text"]
                        context_messages.append(f"{role}: {content}")
                context = "\n".join(context_messages)
                # Add context to agent's system prompt.
                event.agent.system_prompt += f"\n\nRecent conversation:\n{context}"
                logger.info(f"Loaded {len(recent_turns)} conversation turns")

        except Exception as e:
            logger.error(f"Memory load error: {e}")

    def on_message_added(self, event: MessageAddedEvent):
        """Store messages in memory"""
        messages = event.agent.messages
        try:
            # Get session info from agent state
            actor_id = event.agent.state.get("actor_id")
            session_id = event.agent.state.get("session_id")

            if messages[-1]["content"][0].get("text"):
                self.memory_client.create_event(
                    memory_id=self.memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=[(messages[-1]["content"][0]["text"], messages[-1]["role"])]
                )
        except Exception as e:
            logger.error(f"Memory save error: {e}")

    def register_hooks(self, registry: HookRegistry):
        # Register memory hooks
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
