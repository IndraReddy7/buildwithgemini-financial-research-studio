# Financial Research Studio

An intelligent, conversational financial research assistant built with Google Agent Development Kit (ADK), Vertex AI Memory Bank, and Agent Platform. Financial Research Studio standardizes multi-company financial data, normalizes currencies (INR/USD), computes deterministic equity KPIs inside a Python sandbox, and delivers structured A2UI card layouts alongside AI-generated financial infographics and motion videos.

![Financial Research Studio Demo](demo.gif)

---

## Capabilities & Google Cloud Services

Financial Research Studio integrates the following Google Cloud and Agent Platform capabilities:

* **Conversational Agent Engine**: Built with Google ADK (`google-adk`), orchestrating multi-step workflows using `gemini-2.5-flash` with automatic tool calling and structured A2UI responses.
* **Vertex AI Memory Bank**: Integrates `VertexAiMemoryBankService` to record user research preferences, target watchlists, and currency defaults across sessions.
* **Firestore Data Persistence**: Stores and queries standardized company financial metrics (Revenue, Net Income, Shareholder Equity, EPS) for target companies (JPMorgan Chase, Goldman Sachs, Accenture, TCS, and Infosys).
* **Python Code Sandbox Execution**: Executes code via `AgentEngineSandboxCodeExecutor` inside an isolated Agent Engine container for deterministic financial calculations and KPI verification.
* **AI Image Generation**: Uses `gemini-3.1-flash-lite-image` (`generate_domain_image`) to create custom financial infographic visuals, uploaded directly to Google Cloud Storage.
* **AI Video Generation**: Uses Google's Omni model (`gemini-omni-flash-preview`) in the `global` region (`generate_domain_video`) to generate short motion graphic overviews, saved to ADK Playground Artifacts and uploaded to Google Cloud Storage.
* **Live Market & Economic Data Connectors**:
  * Real-time exchange rate conversions via the open Frankfurter API.
  * Real-time stock prices, market capitalization, and trading volume via Yahoo Finance (`yfinance`).
  * Corporate press releases and market news via Google News RSS feeds.
* **Visual Charting Engine**: Generates financial dashboard charts using Matplotlib, uploaded to Cloud Storage for display.
* **A2UI Rendering Engine**: Formats agent responses into structured UI surfaces (`Card`, `Column`, `Row`, `Text`, `Image`) rendered natively in the web chat interface.
* **A2A Proxy Web Frontend**: Lightweight FastAPI proxy bridging browser clients to deployed agent runtime instances over the A2A protocol.

---

## Domain & Target Watchlist

The platform standardizes metrics across US GAAP and IndAS reporting standards:
* **US Market (USD)**: JPMorgan Chase (`JPMC`), Goldman Sachs (`GS`), Accenture (`ACN`)
* **Indian Market (INR / USD)**: Tata Consultancy Services (`TCS`), Infosys (`INFY`)

---

## Project Structure

```
financial-research-studio/
├── app/
│   ├── agent.py              # Core ADK agent definition, tools, and callbacks
│   └── a2ui_utils.py          # A2UI catalog, schema manager, and output parser
├── frontend/
│   ├── main.py               # FastAPI proxy server (A2A protocol bridge)
│   ├── requirements.txt      # Frontend runtime dependencies
│   └── static/
│       └── index.html        # Custom chat interface & built-in A2UI renderer
├── agents-cli-manifest.yaml  # Agent deployment configuration
├── deploy.sh                 # Automated cross-account GCP deployment script
├── project_brief.md          # Project domain brief and specification
├── demo.gif                  # Recorded interaction demonstration
└── README.md                 # Project documentation
```

---

## Automated Cross-Account GCP Deployment

To deploy this entire project into a new Google Cloud Platform account with a single command, run the automated `deploy.sh` script:

```bash
./deploy.sh
```

### What `deploy.sh` Handles Automatically:
1. **API Provisioning**: Enables `aiplatform`, `run`, `firestore`, `storage`, `cloudbuild`, and `iam` APIs.
2. **Cloud Storage Asset Bucket**: Creates a public GCS bucket (`gs://<PROJECT_ID>-financial-studio-assets`) with object-viewer access for generated infographics and videos.
3. **Firestore Initialization**: Initializes a Native-mode Firestore database for financial metric persistence.
4. **Agent Runtime Deployment**: Deploys the ADK agent engine via `agents-cli deploy` and extracts the generated Reasoning Engine resource name.
5. **IAM Service Account Bindings**:
   - Grants `roles/datastore.user` and GCS `roles/storage.objectAdmin` to the Agent Engine service account.
   - Grants `roles/aiplatform.user` to the Cloud Run compute service account so the frontend proxy can reach the agent over A2A.
6. **Frontend Proxy Deployment**: Deploys the FastAPI chat UI to Cloud Run with environment variables pre-configured.

---

## Manual Deployment Workflow

### Deploy Agent to Agent Runtime
```bash
agents-cli deploy
```

### Deploy Frontend Proxy to Cloud Run
```bash
gcloud run deploy financial-research-studio-frontend \
  --source ./frontend \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="<YOUR_DEPLOYED_REASONING_ENGINE_ID>",AGENT_DIRECTORY="app"
```
