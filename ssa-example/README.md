# ssa-example

Simple example of generating access tokens for [Secure Service Accounts](https://aps.autodesk.com/en/docs/ssa/v1/developers_guide/overview/).

## Usage

- Setup virtual environment: `python3 -m venv .venv`
- Install dependencies: `pip install -r requirements.txt`
- Set all the required environment variables, or create a `.env` file with all the variables:
    - `APS_CLIENT_ID` - Autodesk Platform Services client ID (note: the APS application must be of type `Server-to-Server`)
    - `APS_CLIENT_SECRET` - Autodesk Platform Services client secret
    - `SSA_ID` - Secure Service Account ID
    - `SSA_KEY_ID` - Secure Service Account private key ID
    - `SSA_PRIVATE_KEY` - Secure Service Account private key
- Run the script: `python main.py`
- The script will output a JSON object with access token:

```json
{
    "access_token": "eyJhbGci...",
    "token_type": "Bearer",
    "expires_in": 3600
}
```
