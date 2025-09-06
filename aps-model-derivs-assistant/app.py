from uuid import uuid4
from bedrock_agentcore import BedrockAgentCoreApp
from fastapi.middleware.cors import CORSMiddleware
from src.agent import create_design_agent


message_history = {}
app = BedrockAgentCoreApp()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.entrypoint
async def agent_invocation(payload):
    """
    Main handler for agent invocation with streaming response.
    
    This function processes incoming requests, initializes the agent with appropriate tools,
    streams the response back to the client, and saves conversation history.
    
    Expected payload structure:
    {
        "session_id": "optional-session-id",
        "prompt": "Your design data question",
        "aps_design_urn": "APS design URN",
        "aps_access_token": "APS access token",
    }

    Returns:
        Generator: Yields response chunks for streaming
    """
    try:
        user_message = payload.get("prompt", "No prompt found in input, please guide customer to create a json payload with prompt key")
        session_id = payload.get("session_id", str(uuid4()))
        aps_design_urn = payload.get("aps_design_urn")
        aps_access_token = payload.get("aps_access_token")

        print("Request received:")
        print(f"Session ID: {session_id}")
        print(f"APS Design URN: {aps_design_urn}")
        print(f"Prompt: {user_message}")

        messages = message_history.get(session_id, [])
        agent = await create_design_agent(aps_design_urn, aps_access_token, messages)
        stream = agent.stream_async(user_message)
        async for event in stream:
            if "message" in event and "content" in event["message"] and "role" in event["message"] and event["message"]["role"] == "assistant":
                for content_item in event["message"]["content"]:
                    if "toolUse" in content_item and "input" in content_item["toolUse"] and content_item["toolUse"]["name"] == "execute_sql_query":
                        yield f" {content_item["toolUse"]["input"]["description"]}.\n\n"
                    elif "toolUse" in content_item and "name" in content_item["toolUse"] and content_item["toolUse"]["name"] == "get_tables_information":
                        yield "\n\n"
                    elif "toolUse" in content_item and "name" in content_item["toolUse"] and content_item["toolUse"]["name"] == "current_time":
                        yield "\n\n"
            elif "data" in event:
                yield event["data"]

        message_history[session_id] = agent.messages
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        yield error_message


if __name__ == "__main__":
    app.run()
