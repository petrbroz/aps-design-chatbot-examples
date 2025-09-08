# aps-model-derivs-assistant

Experimental chatbot for querying design data in [Autodesk Construction Cloud](https://construction.autodesk.com/) using custom [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore) and [Autodesk Platform Services](https://aps.autodesk.com).

![Thumbnail](thumbnail.png)

## How does it work?

For any design selected in the frontend, the application extracts its various properties using the [Model Derivatives API](https://aps.autodesk.com/en/docs/model-derivative/v2/developers_guide/overview/), and caches the data in a local [sqlite](https://www.sqlite.org) database. Then, the application uses a [Strands Agents](https://strandsagents.com/latest) to query the database based on user prompts.

## Development

### Prerequisites

- Python 3.13 and [uv](https://github.com/astral-sh/uv)
- Autodesk Platform Services application (must be of type _Desktop, Mobile, Single-Page App_)
- Amazon Bedrock AgentCore

### Setup

- Create virtual environment: `uv venv && source .venv/bin/activate`
- Install dependencies: `uv sync`
- Update [www/config.js](www/config.js) with your APS application's client ID
- Configure your AWS credentials

### Run

- Run the backend service: `uv run app.py`
- Serve the web frontend: `python3 -m http.server -d www 8000`
- Go to [http://localhost:8000](http://localhost:8000)
