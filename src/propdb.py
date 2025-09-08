import asyncio
import httpx
import logging
import sqlite3


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelDerivativesClient:
    def __init__(self, access_token: str, host: str = "https://developer.api.autodesk.com"):
        self.client = httpx.AsyncClient()
        self.access_token = access_token
        self.host = host

    async def _get(self, endpoint: str) -> dict:
        response = await self.client.get(f"{self.host}/{endpoint}", headers={"Authorization": f"Bearer {self.access_token}"})
        while response.status_code == 202:
            await asyncio.sleep(1)
            response = await self.client.get(f"{self.host}/{endpoint}", headers={"Authorization": f"Bearer {self.access_token}"})
        if response.status_code >= 400:
            raise Exception(response.text)
        return response.json()

    async def list_model_views(self, urn: str) -> dict:
        json = await self._get(f"modelderivative/v2/designdata/{urn}/metadata")
        return json["data"]["metadata"]

    async def fetch_object_tree(self, urn: str, model_guid: str) -> dict:
        json = await self._get(f"modelderivative/v2/designdata/{urn}/metadata/{model_guid}")
        return json["data"]["objects"]

    async def fetch_all_properties(self, urn: str, model_guid: str) -> dict:
        json = await self._get(f"modelderivative/v2/designdata/{urn}/metadata/{model_guid}/properties")
        return json["data"]["collection"]


def _parse_length(value):
    units = {
        "m": 1,
        "cm": 0.01,
        "mm": 0.001,
        "km": 1000,
        "in": 0.0254,
        "ft": 0.3048,
        "fractional-in": 0.3048,
        "ft-and-fractional-in": 0.3048,
        "yd": 0.9144,
        "mi": 1609.34
    }
    number, unit = value.split()
    return float(number) * units[unit]

def _parse_area(value):
    units = {
        "m^2": 1,
        "cm^2": 0.0001,
        "mm^2": 0.000001,
        "km^2": 1000000,
        "in^2": 0.00064516,
        "ft^2": 0.092903,
        "yd^2": 0.836127,
        "mi^2": 2589988.11
    }
    number, unit = value.split()
    return float(number) * units[unit]

def _parse_volume(value):
    units = {
        "m^3": 1,
        "cm^3": 0.000001,
        "mm^3": 0.000000001,
        "km^3": 1000000000,
        "in^3": 0.0000163871,
        "ft^3": 0.0283168,
        "CF": 0.0283168,
        "yd^3": 0.764555
    }
    number, unit = value.split()
    return float(number) * units[unit]

def _parse_angle(value):
    units = {
        "degrees": 1,
        "degree": 1,
        "deg": 1,
        "°": 1,
        "radians": 57.2958,
        "radian": 57.2958,
        "rad": 57.2958,
    }
    number, unit = value.split()
    return float(number) * units[unit]


# Define the properties to extract from the model
# (column name, column type, category name, property name, parsing function)
PROPERTIES = [
    ("width",       "REAL", "Dimensions",               "Width",                _parse_length),
    ("height",      "REAL", "Dimensions",               "Height",               _parse_length),
    ("length",      "REAL", "Dimensions",               "Length",               _parse_length),
    ("area",        "REAL", "Dimensions",               "Area",                 _parse_area),
    ("volume",      "REAL", "Dimensions",               "Volume",               _parse_volume),
    ("perimeter",   "REAL", "Dimensions",               "Perimeter",            _parse_length),
    ("slope",       "REAL", "Dimensions",               "Slope",                _parse_angle),
    ("thickness",   "REAL", "Dimensions",               "Thickness",            _parse_length),
    ("radius",      "REAL", "Dimensions",               "Radius",               _parse_length),
    ("level",       "TEXT", "Constraints",              "Level",                lambda x: x),
    ("material",    "TEXT", "Materials and Finishes",   "Structural Material",  lambda x: x),
]


def _create_categories_map(root):
    category_map = {}
    def _traverse(node, path):
        if "objects" in node:
            path = node["name"] if path == "" else path + " > " + node["name"]
            for child in node["objects"]:
                _traverse(child, path)
        else:
            category_map[node["objectid"]] = path
    _traverse(root, "")
    return category_map


def get_property_db_schema() -> str:
    return f"CREATE TABLE properties (object_id INTEGER, name TEXT, external_id TEXT, category TEXT, {", ".join([f'{column_name} {column_type}' for (column_name, column_type, _, _, _) in PROPERTIES])})"


async def save_property_db(urn: str, access_token: str, sqlite_db_path: str):
    logger.info(f"Saving property DB to {sqlite_db_path}")
    model_derivative_client = ModelDerivativesClient(access_token)
    views = await model_derivative_client.list_model_views(urn)
    view_guid = views[0]["guid"] # Use the first view
    tree = await model_derivative_client.fetch_object_tree(urn, view_guid)
    categories_map = _create_categories_map(tree[0])
    props = await model_derivative_client.fetch_all_properties(urn, view_guid)
    conn = sqlite3.connect(sqlite_db_path)
    c = conn.cursor()
    db_schema = get_property_db_schema()
    c.execute(db_schema)
    for row in props:
        object_id = row["objectid"]
        name = row["name"]
        external_id = row["externalId"]
        category = categories_map.get(object_id, "")
        object_props = row["properties"]
        insert_values = [object_id, name, external_id, category]
        for (_, _, category_name, property_name, parse_func) in PROPERTIES:
            if category_name in object_props and property_name in object_props[category_name]:
                insert_values.append(parse_func(object_props[category_name][property_name]))
            else:
                insert_values.append(None)
        c.execute(f"INSERT INTO properties VALUES ({', '.join(['?' for _ in insert_values])})", insert_values)
    conn.commit()
    conn.close()


def query_property_db(sqlite_query: str, sqlite_db_path: str) -> str:
    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(sqlite_query)
        rows = cursor.fetchall()
        result = "\n".join([str(row) for row in rows])
    except Exception as e:
        result = f"An error occurred: {e}"
    finally:
        conn.close()
    return result
