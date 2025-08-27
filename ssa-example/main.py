import jwt, time, requests, os, json, sys

def generate_jwt_assertion(aps_client_id: str, ssa_id: str, scopes: list[str], ssa_key_id: str, ssa_private_key: str) -> str:
    """
    Generates a JWT assertion for Autodesk APS authentication.

    Args:
        aps_client_id (str): The Autodesk Platform Services (APS) client ID.
        ssa_id (str): The Secure Service Account ID.
        scopes (list[str]): List of scopes to be included in the JWT, specifying the permissions requested.
        ssa_key_id (str): The key ID (kid) associated with the Secure Service Account.
        ssa_private_key (str): The Secure Service Account private key in PEM format used to sign the JWT.

    Returns:
        str: The encoded JWT assertion as a string.
    """
    payload = {
        "iss": aps_client_id,
        "sub": ssa_id,
        "aud": "https://developer.api.autodesk.com/authentication/v2/token",
        "exp": int(time.time()) + 300,
        "scope": scopes
    }
    return jwt.encode(payload, ssa_private_key, algorithm="RS256", headers={"alg": "RS256", "kid": ssa_key_id})

def get_access_token(aps_client_id: str, aps_client_secret: str, ssa_id: str, ssa_key_id: str, ssa_private_key: str, scopes: list[str]) -> dict:
    """
    Obtain an access token from Autodesk's Authentication API using JWT bearer flow.

    Args:
        aps_client_id (str): The Autodesk Platform Services (APS) client ID.
        aps_client_secret (str): The Autodesk Platform Services (APS) client secret.
        ssa_id (str): The Secure Service Account ID.
        ssa_key_id (str): The key ID (kid) associated with the Secure Service Account.
        ssa_private_key (str): The private key in PEM format associated with the Secure Service Account, used to sign the JWT.
        scopes (list[str]): A list of scopes to request for the access token.

    Returns:
        dict: The JSON response from the authentication API containing the access token and related information.
    """
    jwt_assertion = generate_jwt_assertion(aps_client_id, ssa_id, scopes, ssa_key_id, ssa_private_key)
    response = requests.post("https://developer.api.autodesk.com/authentication/v2/token", headers={
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_assertion,
        "scope": " ".join(scopes),
        "client_id": aps_client_id,
        "client_secret": aps_client_secret
    })
    return response.json()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    aps_client_id = os.environ["APS_CLIENT_ID"]
    aps_client_secret = os.environ["APS_CLIENT_SECRET"]
    ssa_id = os.environ["SSA_ID"]
    ssa_key_id = os.environ["SSA_KEY_ID"]
    ssa_private_key = os.environ["SSA_PRIVATE_KEY"].replace("\\n", "\n")
    if not aps_client_id or not aps_client_secret or not ssa_id or not ssa_key_id or not ssa_private_key:
        print("Error: Missing required environment variables.")
        sys.exit(1)
    result = get_access_token(aps_client_id, aps_client_secret, ssa_id, ssa_key_id, ssa_private_key, scopes=["data:read"])
    print(json.dumps(result, indent=4))
