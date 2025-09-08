import logging
import jwt
from bedrock_agentcore import BedrockAgentCoreApp
from fastapi.middleware.cors import CORSMiddleware
from src.agent import create_design_agent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        "aps_design_urn": "APS design URN",
        "aps_access_token": "APS access token",
        "prompt": "Your design data question",
    }

    Returns:
        Generator: Yields response chunks for streaming
    """
    try:
        prompt = payload.get("prompt", "No prompt found in input, please guide customer to create a json payload with prompt key")
        aps_design_urn = payload.get("aps_design_urn")
        aps_access_token = payload.get("aps_access_token")
        logger.info("Request received:")
        logger.info(f"Design URN: {aps_design_urn}")
        logger.info(f"Prompt: {prompt}")

        user_id = None
        if aps_access_token:
            try:
                decoded_token = jwt.decode(aps_access_token, options={"verify_signature": False})
                user_id = decoded_token.get("userid")
                logger.info(f"User ID: {user_id}")
            except Exception as e:
                logger.error(f"Failed to decode JWT: {e}")

        agent = await create_design_agent(aps_design_urn, user_id, aps_access_token)
        stream = agent.stream_async(prompt)
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
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        yield error_message


if __name__ == "__main__":
    app.run()
