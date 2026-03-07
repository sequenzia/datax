DataX is an Agentic AI Data Analytics App. A sort of. "Chat with your data" type of app. It is designed to help users analyze and understand their data through natural language queries. The app uses advanced AI techniques to interpret user queries and provide insights based on the data provided. This app will need to utilize both Python and Typescript. 

MVP Features:

- Allow users to upload their data in various formats (CSV, Excel, Parquet, JSON, etc.).
- Allow users to setup connections to databases (PostgreSQL, MySQL, etc.).
- Allow users to ask questions about their data in natural language.
- Provide insights and visualizations based on the user's queries.
- A virtual data layer that abstracts away the underlying data sources and allows for seamless querying across multiple datasets and connections.
- An agentic AI layer that can interpret user queries, determine the necessary data sources, and generate appropriate SQL queries to retrieve the required information.
- A SQL editor for users who prefer to write their own queries.
- A dashboard to view and manage uploaded datasets and connections.
- Support for multiple model providers (OpenAI, Anthropic, Google Gemini, OpenAI Compatible) to ensure flexibility.

Technical Details:

The following libraries and frameworks should be considered for the implementation of DataX. This is not an exhaustive list, but it provides a starting point for the technologies that could be used in the app. If any of the libraries or frameworks are not suitable, feel free to suggest alternatives.

Python:

- Pydantic AI: AI layer for interfacing with models and building agents
- Pydantic: Data validation
- Pydantic Settings: Configuration management
- UV: Package manager
- DuckDB: Database engine for virtual data layer and querying data
- SQLAlchemy: Database toolkit for Python
- FastAPI: Web framework for building the backend API

Typescript:

- React: Frontend library for building user interfaces
- Tailwind CSS: Utility-first CSS framework for styling
- shadcn/ui: Component library for building the user interface
- Vercel ai-sdk: SDK for integrating AI capabilities into the frontend
- Vercel ai-elements: Pre-built AI components for the frontend
- Tambo AI: AI agent framework for building conversational interfaces
- Streamdown: Streaming markdown renderer for React

Open questions:
- Next.js or Vite + React for the frontend framework?
- Visualization library for insights and visualizations (e.g., D3.js, Chart.js, Recharts, Plotly)?

