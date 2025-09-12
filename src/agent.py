import logging
import json
import os
import re
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from strands import Agent
from src.memory import MemoryHookProvider


MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
MEMORY_ID = "DesignAgentMemory-oBupukC2Dp"
with open("SYSTEM_PROMPT.md", "r") as f:
    SYSTEM_PROMPT = f.read()
logger = logging.getLogger(__name__)


def create_design_agent(aps_design_urn: str, user_id: str, props_cache_folder: str):
    logger.info(f"Creating design agent for design URN: {aps_design_urn}, user ID: {user_id}, props cache folder: {props_cache_folder}")

    @tool
    def list_property_categories() -> list[str]:
        """
        List all property categories available in the design.

        Returns:
            list[str]: List of property category names.
        """
        logger.info(f"Listing property categories from {aps_design_urn}")
        try:
            with open(os.path.join(props_cache_folder, "props.json"), "r") as f:
                elements = json.load(f)

            categories = set()
            for element in elements:
                element_props = element.get("properties", {})
                categories.update(element_props.keys())

            categories = sorted(categories)
            logger.info(f"Found property categories:\n{categories}")
            return categories

        except Exception as e:
            logger.error(f"Error occurred while listing property categories: {e}")
            return [f"An error occurred: {e}"]

    @tool
    def list_property_types(category: str) -> list[dict]:
        """
        List all unique property types in a given category.

        Returns:
            list[dict]: List of unique property types with their names and units.
        """
        logger.info(f"Extracting property types for category '{category}' from {aps_design_urn}")
        try:
            with open(os.path.join(props_cache_folder, "props.json"), "r") as f:
                elements = json.load(f)

            unique_properties = {}

            for element in elements:
                category_props = element.get("properties", {}).get(category, {})
                if isinstance(category_props, dict):
                    for prop_name, prop_value in category_props.items():
                        if prop_name not in unique_properties:
                            # Extract unit if the value is a number followed by space and unit
                            unit = None
                            if isinstance(prop_value, str):
                                # Pattern to match number (including decimals) followed by space and unit
                                unit_match = re.match(r'^[\d.,]+\s+(.+)$', prop_value.strip())
                                if unit_match:
                                    unit = unit_match.group(1)
                            unique_properties[prop_name] = {
                                "name": prop_name,
                                "unit": unit
                            }

            unique_properties = list(unique_properties.values())
            logger.info(f"Extracted property types: {unique_properties}")
            return unique_properties

        except Exception as e:
            logger.error(f"Error occurred while extracting property types: {e}")
            return f"An error occurred: {e}"

    @tool
    def execute_python_code(code: str) -> str:
        """
        Execute custom Python code. The code has access to `tree.json` and `props.json` files with design data.

        Args:
            code (str): The Python code to execute.

        Returns:
            str: The STDOUT of the code execution.
        """
        logger.info("Executing Python code:\n" + "\n".join(f"    {line}" for line in code.splitlines()))
        try:
            def read_cache_file(filename: str):
                with open(os.path.join(props_cache_folder, filename), "r") as f:
                    return f.read()
            files_to_create = [{"path": filename, "text": read_cache_file(filename)} for filename in ["tree.json", "props.json"]]
            code_client = CodeInterpreter("us-west-2")
            code_client.start(session_timeout_seconds=15*60)
            response = code_client.invoke("writeFiles", {"content": files_to_create})
            for event in response["stream"]:
                logger.info(f"Writing files to code sandbox: {event}")
            response = code_client.invoke("executeCode", {"code": code, "language": "python", "clearContext": False})
            output = ""
            for event in response["stream"]:
                logger.info(f"Response from Python code: {event}")
                result = event.get("result", {})
                structured_content = result.get("structuredContent", {})
                output += structured_content.get("stdout", "")
            code_client.stop()
            return output
        except Exception as e:
            code_client.stop()
            logger.error(f"Error occurred while executing Python code: {e}")
            return f"An error occurred: {e}"

    return Agent(
        name="APS Design Agent",
        model=BedrockModel(model_id=MODEL_ID),
        hooks=[MemoryHookProvider(MEMORY_ID)],
        tools=[list_property_categories, list_property_types, execute_python_code],
        state={"actor_id": user_id, "session_id": aps_design_urn},
        system_prompt=SYSTEM_PROMPT,
    )
