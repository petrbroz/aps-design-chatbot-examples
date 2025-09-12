import json
import logging
import os
from src.aps import ModelDerivativesClient


logger = logging.getLogger(__name__)


async def cache_design_props(aps_design_urn: str, aps_access_token: str, props_cache_folder: str):
    """
    Cache design properties to a local folder.

    Args:
        aps_design_urn (str): The URN of the APS design.
        aps_access_token (str): The APS access token.
        props_cache_folder (str): The folder to cache properties in.
    """
    logger.info(f"Caching design properties for {aps_design_urn}")
    model_derivative_client = ModelDerivativesClient(aps_access_token)
    views = await model_derivative_client.list_model_views(aps_design_urn)
    view_guid = views[0]["guid"] # Use the first view
    tree = await model_derivative_client.fetch_object_tree(aps_design_urn, view_guid)
    with open(os.path.join(props_cache_folder, "tree.json"), "w") as f:
        json.dump(tree, f, indent=2)
    props = await model_derivative_client.fetch_all_properties(aps_design_urn, view_guid)
    with open(os.path.join(props_cache_folder, "props.json"), "w") as f:
        json.dump(props, f, indent=2)
