> IMPORTANT: this project has been moved to https://github.com/autodesk-platform-services/aps-design-chatbot-examples.

<br/>
<br/>
<br/>
<br/>
<br/>
<br/>
<br/>
<br/>

# APS Design Chatbots

This repository contains several experimental chatbot applications designed to interact with design data hosted in [Autodesk Construction Cloud](https://construction.autodesk.com/) (ACC). Each chatbot leverages [Autodesk Platform Services](https://aps.autodesk.com/) (APS) and custom [LangChain](https://www.langchain.com/) agents to provide advanced querying and data analytics capabilities.

## Examples

### APS Model Derivatives Assistant

- **Purpose**: Facilitates querying of design data properties stored in a local SQLite database, extracted using the Model Derivatives API.
- **Features**:
  - Extracts and caches design properties locally.
  - Uses a LangChain agent to query the database based on user prompts.
  - Supports queries like finding elements with the largest area or calculating aggregate values.
- **Usage**: Users can log in, select a design file, and perform data analytics on extracted properties.

### ACC Model Properties Assistant

- **Purpose**: Enables querying of design element properties using the ACC Model Properties API.
- **Features**:
  - Implements a LangChain agent with tools for interacting with the ACC Model Properties API.
  - Supports creating and querying property indices for design files.
  - Includes a guide for the Model Properties Query Language (MPQL).
- **Usage**: Users can log in, select a design file, and query properties such as wall volumes or IDs of elements matching specific criteria.

### AEC Data Model Assistant

- **Purpose**: Provides advanced querying capabilities for AEC (Architecture, Engineering, and Construction) data using the AEC Data Model API.
- **Features**:
  - Implements a LangChain agent with tools for executing GraphQL queries.
  - Supports filtering, pagination, and property definition retrieval.
  - Includes documentation for API constructs and filtering options.
- **Usage**: Users can query elements, retrieve property definitions, and analyze data using prompts.

## Setup & Development

Refer to the `README.md` files in each subproject directory for specific setup instructions, prerequisites, and usage examples.

## License

This sample is licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). See [LICENSE.md](LICENSE.md) file for more details.
