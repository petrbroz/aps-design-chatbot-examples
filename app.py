import json
import jwt
import logging
import os
import re
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from fastapi.middleware.cors import CORSMiddleware
from strands import Agent
from src.aps import ModelDerivativesClient
from src.memory import MemoryHookProvider


MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
MEMORY_ID = "DesignAgentMemory-oBupukC2Dp"
CACHE_FOLDER = "cache"
with open("SYSTEM_PROMPT.md", "r") as f:
    SYSTEM_PROMPT = f.read()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cache_design_props(aps_design_urn: str, aps_access_token: str, props_cache_folder: str):
    logger.info(f"cache_design_props: {aps_design_urn}")
    model_derivative_client = ModelDerivativesClient(aps_access_token)
    views = await model_derivative_client.list_model_views(aps_design_urn)
    with open(os.path.join(props_cache_folder, "views.json"), "w") as f:
        json.dump(views, f, indent=2)
    view_guid = views[0]["guid"] # Use the first view
    tree = await model_derivative_client.fetch_object_tree(aps_design_urn, view_guid)
    with open(os.path.join(props_cache_folder, "tree.json"), "w") as f:
        json.dump(tree, f, indent=2)
    props = await model_derivative_client.fetch_all_properties(aps_design_urn, view_guid)
    with open(os.path.join(props_cache_folder, "props.json"), "w") as f:
        json.dump(props, f, indent=2)


def create_design_agent(aps_design_urn: str, user_id: str, props_cache_folder: str):
    @tool
    def extract_property_types() -> str:
        """
        Extract and return all unique property types for the design.

        Returns:
            str: JSON list of unique property types with their names, categories, and units.
        """
        try:
            with open(os.path.join(props_cache_folder, "props.json"), "r") as f:
                elements = json.load(f)

            unique_properties = {}

            for element in elements:
                categories = element.get("properties", {})
                # Iterate through each category in the properties
                for category_name, category_props in categories.items():
                    if isinstance(category_props, dict):
                        # Iterate through each property in the category
                        for prop_name, prop_value in category_props.items():
                            # Create a unique key for the property
                            prop_key = f"{category_name}::{prop_name}"
                            if prop_key not in unique_properties:
                                # Extract unit if the value is a number followed by space and unit
                                unit = None
                                if isinstance(prop_value, str):
                                    # Pattern to match number (including decimals) followed by space and unit
                                    unit_match = re.match(r'^[\d.,]+\s+(.+)$', prop_value.strip())
                                    if unit_match:
                                        unit = unit_match.group(1)
                                unique_properties[prop_key] = {
                                    "name": prop_name,
                                    "category": category_name,
                                    "unit": unit
                                }

            unique_properties = list(unique_properties.values())
            logger.info(f"extract_property_types:\n{unique_properties}")
            return json.dumps(unique_properties, indent=2)

        except Exception as e:
            logger.error(f"extract_property_types: {e}")
            return f"An error occurred: {e}"

    @tool
    def execute_python_code(code: str) -> str:
        """
        Execute custom Python code. The code has access to `views.json`, `tree.json`, and `props.json` files with design data.

        Args:
            code (str): The Python code to execute.

        Returns:
            str: The STDOUT of the code execution.
        """
        try:
            logger.info(f"execute_python_code:\n{code}")
            def read_cache_file(filename: str):
                with open(os.path.join(props_cache_folder, filename), "r") as f:
                    return f.read()
            files_to_create = [{"path": filename, "text": read_cache_file(filename)} for filename in ["views.json", "tree.json", "props.json"]]
            code_client = CodeInterpreter("us-west-2")
            code_client.start(session_timeout_seconds=15*60)
            response = code_client.invoke("writeFiles", {"content": files_to_create})
            for event in response["stream"]:
                logger.info(f"execute_python_code:write_files: {event}")
            response = code_client.invoke("executeCode", {"code": code, "language": "python", "clearContext": False})
            output = ""
            for event in response["stream"]:
                logger.info(f"execute_python_code:execute_code: {event}")
                structured_content = event.get("structuredContent", {})
                output += structured_content.get("stdout", "")
            code_client.stop()
            return output
        except Exception as e:
            code_client.stop()
            logger.error(f"execute_python_code: {e}")
            return f"An error occurred: {e}"

    return Agent(
            name="APS Design Agent",
            model=BedrockModel(model_id=MODEL_ID),
            hooks=[MemoryHookProvider(MEMORY_ID)],
            tools=[extract_property_types, execute_python_code],
            state={"actor_id": user_id, "session_id": aps_design_urn},
            system_prompt=SYSTEM_PROMPT,
        )


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

        # Extract user ID from the access token
        user_id = None
        if aps_access_token:
            try:
                decoded_token = jwt.decode(aps_access_token, options={"verify_signature": False})
                user_id = decoded_token.get("userid")
                logger.info(f"User ID: {user_id}")
            except Exception as e:
                logger.error(f"Failed to decode JWT: {e}")

        # Cache design properties if not already cached
        props_cache_folder = os.path.join(CACHE_FOLDER, aps_design_urn)
        if not os.path.exists(props_cache_folder):
            os.makedirs(props_cache_folder)
            await cache_design_props(aps_design_urn, aps_access_token, props_cache_folder)

        # Create the agent
        agent = create_design_agent(aps_design_urn, user_id, props_cache_folder)
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
