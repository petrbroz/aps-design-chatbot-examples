# aps-design-assistant

Experimental chatbot for querying design data in [Autodesk Construction Cloud](https://construction.autodesk.com/) using custom [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore) and [Autodesk Platform Services](https://aps.autodesk.com).

![Thumbnail](thumbnail.png)

## How does it work?

For any selected design file, the application extracts its various properties using the [Model Derivatives API](https://aps.autodesk.com/en/docs/model-derivative/v2/developers_guide/overview/), and caches them in a local [sqlite](https://www.sqlite.org) database. Then, the application uses a [Strands Agents](https://strandsagents.com/latest) to query the database based on user prompts.

## Development

### Prerequisites

- Python 3.13 and [uv](https://github.com/astral-sh/uv)
- Autodesk Platform Services application (must be of type _Desktop, Mobile, Single-Page App_)
- AWS credentials
- Access to Amazon Bedrock AgentCore

### Setup

- Create virtual environment: `uv venv && source .venv/bin/activate`
- Install dependencies: `uv sync`
- Setup AgentCore Memory: `python scripts/create_agentcore_memory.py SomeMemoryName`
- Update the `MEMORY_ID` in [src/config.py](src/config.py) with the newly created memory ID
- Configure the AgentCore Runtime: `agentcore configure -e app.py`
- Deploy to AgentCore Runtime: `agentcore launch`

### Try it out

#### Locally running agent with a simple website

1. Add the APS client ID `YmHvRac8ZID6GHVY3R9skAcVZ8joHmyYT1RH7mvic7kEpTM9` as a custom integration to one of your ACC projects
2. Run the AgentCore Runtime locally: `uv run app.py`
3. Serve the static website under the _www_ folder: `python3 -m http.server -d www 8000`
4. Go to [http://localhost:8000](http://localhost:8000)
5. Login with your Autodesk credentials
6. Select a design file, and start asking questions

#### Invoking AgentCore Runtime from command line

1. Go to https://acc.autodesk.com, open one of your design files, a design URN and an access token from the Network tab, and set them as environment variables:

```bash
export APS_DESIGN_URN="dXJuOmFk..."
export APS_ACCESS_TOKEN="eyJhbGci..."
```

2. Invoke the remote agent:

```bash
agentcore invoke "{\"prompt\":\"What are the top 5 elements with largest volume?\", \"aps_design_urn\":\"$APS_DESIGN_URN\",\"aps_access_token\":\"$APS_ACCESS_TOKEN\"}"
```
