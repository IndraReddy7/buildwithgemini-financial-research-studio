# Financial Research Studio — Technical Deep Dive & Architecture

This document provides a comprehensive technical breakdown of the **Financial Research Studio** agent, its underlying Google Cloud Platform (GCP) services, connectors, execution sandboxes, workflows, and estimated operational costs.

---

## 1. Executive Summary & Purpose

**Financial Research Studio** is an enterprise equity research and financial analytics assistant built using the **Google Agent Development Kit (ADK)** and deployed on **Vertex AI Agent Platform**. 

### Core Problem Solved
Financial analysts frequently deal with disparate reporting standards (US GAAP in USD vs. IndAS/IFRS in INR) and non-standardized quarter alignments across global markets. Off-the-shelf LLMs often hallucinate financial figures or fail at precise mathematical ratio calculations.

### Solution Architecture
1. **Deterministic Data Connectors**: Queries structured Firestore financial data and live market endpoints rather than scraping unstructured web text.
2. **Multi-Currency Normalization**: Automatically converts INR/USD metrics using live FX rates from the open Frankfurter API.
3. **Sandbox Calculation**: Executes ratio formulas (Net Margin, Return on Equity, YoY Growth) inside an isolated Python code executor.
4. **Rich Visual Output**: Delivers responses using **A2UI** (Agent-to-User Interface) cards, Matplotlib charts, AI-generated infographics (`gemini-3.1-flash-lite-image`), and motion videos (`gemini-omni-flash-preview`).
5. **Cross-Session Memory**: Persists analyst watchlists and preferences using **Vertex AI Memory Bank**.

---

## 2. Google Cloud Services Used

| Google Cloud Service | Purpose in Architecture | Configuration / Details |
| :--- | :--- | :--- |
| **Vertex AI Agent Platform** | Hosts the deployed ADK agent container (`ReasoningEngine`) | Deployed in `us-east1` via `agents-cli deploy` |
| **Gemini 2.5 Flash** (`gemini-2.5-flash`) | Primary reasoning, tool orchestration, and A2UI generation | Includes HttpRetryOptions (3 attempts) |
| **Gemini 3.1 Flash Lite Image** | Generates custom AI financial infographics and charts | Vertex AI location: `us-east1` |
| **Gemini Omni Flash** (`gemini-omni-flash-preview`) | Generates short financial motion graphic videos | Vertex AI location: `global` |
| **Vertex AI Memory Bank** | Long-term memory persistence across user chat sessions | Service ID: `VertexAiMemoryBankService` |
| **Firestore (Native Mode)** | NoSQL database storing structured income statements and balance sheets | Database location: `us-east1` |
| **Cloud Storage (GCS)** | Public asset bucket hosting generated charts, infographics, and videos | Bucket: `gs://<project_id>-financial-studio-assets` |
| **Cloud Run** | Serverless hosting for FastAPI A2A proxy and custom chat UI | Region: `us-east1`, min instances: 0 |
| **Cloud Build** | Container build pipeline for Cloud Run and Agent Engine images | Triggered on deployment |
| **Cloud IAM** | Least-privilege role management (`roles/aiplatform.user`, `roles/datastore.user`) | Service account bindings |

---

## 3. Connectors & Tool Ecosystem

The agent uses a suite of custom Python function tools registered on the `root_agent`:

### A. Financial Data Connectors (Firestore)
* **`get_company_financials`**: Retrieves quarterly revenue, net income, shareholder equity, and EPS for target tickers (`JPMC`, `GS`, `ACN`, `TCS`, `INFY`).
* **`list_watchlist_companies`**: Queries all companies stored in the database watchlist.
* **`upsert_company_financials`**: Allows adding or updating financial records in Firestore.

### B. Live External Data Connectors
* **`fetch_live_exchange_rate`**: Fetches live FX conversion rates (e.g. INR to USD) from the free Frankfurter API without needing API keys.
* **`fetch_live_market_data`**: Connects to Yahoo Finance (`yfinance`) for real-time stock prices, 52-week highs/lows, market cap, and volume.
* **`fetch_company_news`**: Retrieves real-time corporate press releases and market news via Google News RSS.

### C. Analytics & Visualization Tools
* **`calculate_normalized_kpis`**: Computes Net Margin ($\frac{\text{Net Income}}{\text{Revenue}}$) and Return on Equity ($\frac{\text{Net Income}}{\text{Equity}}$) across INR and USD.
* **`generate_dashboard_chart`**: Uses Matplotlib to plot bar or line chart comparisons, saves them as PNG, and uploads to GCS.
* **`generate_domain_image`**: Calls `gemini-3.1-flash-lite-image` to generate visual infographics and embeds public URLs in A2UI cards.
* **`generate_domain_video`**: Calls `gemini-omni-flash-preview` in `global` location to produce motion videos, uploaded to GCS and saved as ADK Artifacts.

---

## 4. Execution Sandbox Infrastructure

### Agent Engine Sandbox Code Executor
* **Class**: `AgentEngineSandboxCodeExecutor`
* **Mechanism**: When complex data transformations or custom mathematical models are requested, Gemini generates Python code. This code is passed to an isolated **Agent Engine Sandbox Container**.
* **Security & Isolation**:
  * Runs in a ephemeral, containerized environment managed by Vertex AI.
  * Prevents arbitrary code execution on host machines or Cloud Run containers.
  * Returns execution stdout/stderr directly back to the agent for verification before presenting to the user.

---

## 5. Skills & System Architecture

```
                               ┌─────────────────────────────────────────┐
                               │             User Browser                │
                               └────────────────────┬────────────────────┘
                                                    │ HTTP
                                                    ▼
                               ┌─────────────────────────────────────────┐
                               │       Cloud Run FastAPI Proxy           │
                               │        (A2A Protocol Engine)            │
                               └────────────────────┬────────────────────┘
                                                    │ A2A Protocol
                                                    ▼
                               ┌─────────────────────────────────────────┐
                               │     Vertex AI Reasoning Engine          │
                               │           (ADK Agent)                   │
                               └──────┬──────────────────────┬───────────┘
                                      │                      │
                 ┌────────────────────┴───┐              ┌───┴────────────────────┐
                 │                        │              │                        │
                 ▼                        ▼              ▼                        ▼
      ┌────────────────────┐    ┌──────────────────┐  ┌──────────────────┐    ┌────────────────────┐
      │ Gemini 2.5 Flash   │    │  Firestore DB    │  │ GCS Media Bucket │    │ Agent Engine       │
      │ (Orchestrator)     │    │  (Financials)    │  │ (Images/Videos)  │    │ Python Sandbox     │
      └────────────────────┘    └──────────────────┘  └──────────────────┘    └────────────────────┘
```

### Integrated Skills:
1. **`build-agent-frontend`**: Provides the FastAPI proxy bridge and built-in A2UI card renderer.
2. **`enable-a2ui`**: Generates flat, lightweight A2UI JSON surfaces (`Card`, `Column`, `Row`, `Text`, `Image`).
3. **`setup-memory-bank`**: Integrates `VertexAiMemoryBankService` and `generate_memories_callback` to store facts post-turn.

---

## 6. Comprehensive Cost Estimate

Below is a detailed cost breakdown based on Google Cloud list pricing for a typical **medium production workload (~10,000 queries / month)**:

| Service / Resource | Pricing Metric | Usage Estimate (10k Queries/Mo) | Estimated Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Gemini 2.5 Flash** | $0.075 / 1M input tokens<br>$0.30 / 1M output tokens | ~15M input tokens<br>~3M output tokens | **~$2.03** |
| **Gemini 3.1 Flash Lite Image** | ~$0.002 / generated image | ~200 infographic requests | **~$0.40** |
| **Gemini Omni Flash (Video)** | ~$0.015 / generated video | ~50 video requests | **~$0.75** |
| **Vertex AI Agent Engine** | ~$0.05 / node-hour (scaled to zero) | ~20 active hours | **~$1.00** |
| **Vertex AI Memory Bank** | ~$0.002 / 1,000 vector queries | ~10,000 queries | **~$0.02** |
| **Firestore (Native)** | Free Tier: 50k reads, 20k writes/day | Within Free Tier limits | **$0.00** |
| **Cloud Run (Frontend)** | Free Tier: 2 Million requests/mo | Within Free Tier limits | **$0.00** |
| **Cloud Storage (GCS)** | $0.02 / GB / month | ~5 GB asset storage | **~$0.10** |
| **Networking & Egress** | Free Tier / Standard Egress | ~10 GB traffic | **~$0.12** |
| **TOTAL ESTIMATED COST** | | | **~$4.42 / month** |

> **Note**: For personal development, prototyping, or workshop usage, total costs typically remain under **$1.00 - $3.00 / month** due to Google Cloud's generous free tier allocations.
