# aps-design-assistant

Experimental chatbot for querying design data in [Autodesk Construction Cloud](https://construction.autodesk.com/) using [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore) and [Autodesk Platform Services](https://aps.autodesk.com).

![Thumbnail](thumbnail.png)

## How does it work?

For any selected design file, the application extracts design properties using the [Model Derivatives API](https://aps.autodesk.com/en/docs/model-derivative/v2/developers_guide/overview/), and caches them in JSON files. Then, an AI agent built with [Strands Agents](https://strandsagents.com/latest) is initialized to answer various questions about the design using the following tools:

- Listing names of property categories available in the design (for example, `["Dimensions", "Structural Material"]`)
- Listing names and units of properties in given category (for example, `[{ "name": "Area", "units": "ft^2" }, { "name": "Volume", "units": "ft^3" }]`)
- Executing custom Python code (using [AgentCore Code Interpreter Tool](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html)) with access to the JSON files with design data

The AI agent also uses [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-getting-started.html) for short-term memory (scoped to a specific user and design).

## Development

### Prerequisites

- Python 3.13 and [uv](https://github.com/astral-sh/uv)
- AWS credentials with access to Amazon Bedrock AgentCore

### Setup

- Create and activate a virtual environment: `uv venv && source .venv/bin/activate`
- Install dependencies: `uv sync`
- Setup AgentCore Memory: `python scripts/create_agentcore_memory.py SomeMemoryName`
- Update the `MEMORY_ID` constant in [src/agent.py](src/agent.py) with the newly created memory ID
- Configure the AgentCore Runtime: `agentcore configure -e app.py`
- Deploy to AgentCore Runtime: `agentcore launch`

https://github.com/user-attachments/assets/316ce37f-f916-4ffa-8444-1c6653f80d6e

### Try it out

#### Locally running agent with a simple website

1. Add the APS client ID `YmHvRac8ZID6GHVY3R9skAcVZ8joHmyYT1RH7mvic7kEpTM9` as a custom integration to one of your ACC projects
2. Run the AgentCore Runtime locally: `uv run app.py`
3. Serve the static website under the _www_ folder: `python3 -m http.server -d www 8000`
4. Go to [http://localhost:8000](http://localhost:8000)
5. Login with your Autodesk credentials
6. Select a design file, and start asking questions

https://github.com/user-attachments/assets/1f30ef4d-7b53-4cde-928b-7b2954fccbb8

#### Invoking AgentCore Runtime from command line

1. Go to https://acc.autodesk.com, open one of your design files, and extract a design URN and an access token from the Network tab:

```bash
export APS_DESIGN_URN="dXJuOmFk..."
export APS_ACCESS_TOKEN="eyJhbGci..."
```

2. Invoke the remote agent with the design URN and access token:

```bash
agentcore invoke "{\"prompt\":\"What are the top 5 elements with largest volume?\", \"aps_design_urn\":\"$APS_DESIGN_URN\",\"aps_access_token\":\"$APS_ACCESS_TOKEN\"}"
```

https://github.com/user-attachments/assets/14ce0fea-4e1d-44d7-b4a4-8e36870932cd
