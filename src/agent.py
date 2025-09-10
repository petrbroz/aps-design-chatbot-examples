import os
import logging
from strands import Agent, tool
from strands.models import BedrockModel
from .propdb import save_property_db, query_property_db, get_property_db_schema
from .memory import MemoryHookProvider
from .config import MODEL_ID, MEMORY_ID, CACHE_FOLDER, SYSTEM_PROMPT


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_design_agent(aps_design_urn: str, user_id: str, aps_access_token: str):
    if not aps_design_urn:
        raise ValueError("APS Design URN is required")
    if not aps_access_token:
        raise ValueError("APS Access Token is required")

    sqlite_db_folder = os.path.join(CACHE_FOLDER, aps_design_urn)
    sqlite_db_path = os.path.join(sqlite_db_folder, "propdb.sqlite")
    if not os.path.exists(sqlite_db_folder):
        os.makedirs(sqlite_db_folder)
        logger.info(f"Caching property database: {sqlite_db_path}")
        await save_property_db(aps_design_urn, aps_access_token, sqlite_db_path)
        logger.info(f"Property database cached")

    @tool
    def _query_property_db(sqlite_query: str) -> str:
        """
        Query the design property database using an SQLite query.

        Args:
            sqlite_query (str): The SQLite query to execute.

        Returns:
            str: The result of the SQLite query.
        """
        try:
            logger.info(f"query_property_db: {sqlite_query}")
            result = query_property_db(sqlite_query, sqlite_db_path)
            logger.info(f"query_property_db: {result}")
            return result
        except Exception as e:
            logger.error(f"Error executing SQLite query: {e}")
            return f"An error occurred: {e}"

    @tool
    def _get_property_db_schema() -> str:
        """
        Get the schema of the design property database.

        Returns:
            str: The schema of the design property database.
        """
        try:
            logger.info(f"get_property_db_schema")
            result = get_property_db_schema()
            logger.info(f"get_property_db_schema: {result}")
            return result
        except Exception as e:
            logger.error(f"Error fetching property database schema: {e}")
            return f"An error occurred: {e}"

    return Agent(
        name="APS Design Agent",
        model=BedrockModel(model_id=MODEL_ID),
        hooks=[MemoryHookProvider(MEMORY_ID)],
        tools=[_query_property_db, _get_property_db_schema],
        state={"actor_id": user_id, "session_id": aps_design_urn},
        system_prompt=SYSTEM_PROMPT,
    )
