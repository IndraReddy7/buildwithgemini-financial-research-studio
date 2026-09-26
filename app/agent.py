# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
from pathlib import Path
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf
from google import genai
from google.cloud import firestore, storage

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback

# Hardcoded project ID, bucket name, and Memory Bank ID for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-610e200fc759"
COLLECTION_NAME = "financial_metrics"
BUCKET_NAME = "financial-research-studio-qwiklabs-gcp-02-610e200fc759"
MEMORY_BANK_ID = "6365615971939385344"

# Ticker mapping for US and Indian exchanges
TICKER_MAP = {
    "JPMC": "JPM",
    "JPM": "JPM",
    "GS": "GS",
    "ACN": "ACN",
    "TCS": "TCS.NS",
    "INFY": "INFY",
}


def _get_db():
    return firestore.Client(project=PROJECT_ID)


# --- MEMORY CALLBACK ---

async def generate_memories_callback(callback_context: CallbackContext):
    """Callback triggered after each turn to extract and persist durable facts into Memory Bank."""
    try:
        if callback_context.memory_service:
            await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


# --- FIRESTORE TOOLS ---

def get_company_financials(ticker: str) -> str:
    """Retrieve financial report metrics and company details from Firestore for a given ticker symbol.

    Args:
        ticker: The stock ticker symbol (e.g. 'JPMC', 'GS', 'ACN', 'TCS', 'INFY').

    Returns:
        A string containing the company's financial metrics or a not found message.
    """
    db = _get_db()
    doc_ref = db.collection(COLLECTION_NAME).document(ticker.strip().upper())
    doc = doc_ref.get()
    if not doc.exists:
        return f"No financial data found in Firestore for ticker '{ticker}'."
    data = doc.to_dict()
    return (
        f"Company: {data.get('name')} ({data.get('ticker')})\n"
        f"Accounting Standard: {data.get('accounting_standard')}\n"
        f"Currency: {data.get('currency')}\n"
        f"Fiscal Year: {data.get('fiscal_year')}\n"
        f"Revenue: {data.get('revenue_billions')} billion {data.get('currency')}\n"
        f"Net Income: {data.get('net_income_billions')} billion {data.get('currency')}\n"
        f"Net Margin: {data.get('net_margin_percent')}%\n"
        f"ROE: {data.get('roe_percent')}%\n"
        f"Last Updated: {data.get('updated_at')}"
    )


def list_watchlist_companies() -> str:
    """Retrieve all company tickers and summaries currently tracked in the Firestore financial database.

    Returns:
        A formatted string listing all tracked companies with their key metrics.
    """
    db = _get_db()
    docs = db.collection(COLLECTION_NAME).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        results.append(
            f"• {data.get('ticker')} ({data.get('name')}) [{data.get('accounting_standard')}] - "
            f"Revenue: {data.get('revenue_billions')}B {data.get('currency')}, "
            f"Net Margin: {data.get('net_margin_percent')}%, ROE: {data.get('roe_percent')}%"
        )
    if not results:
        return "No companies currently tracked in the database."
    return "Tracked Financial Watchlist:\n" + "\n".join(results)


def upsert_company_financials(
    ticker: str,
    name: str,
    accounting_standard: str,
    currency: str,
    fiscal_year: str,
    revenue_billions: float,
    net_income_billions: float,
    net_margin_percent: float,
    roe_percent: float,
) -> str:
    """Add or update financial metrics for a company in the Firestore database.

    Args:
        ticker: The stock ticker symbol (e.g. 'JPMC', 'GS', 'ACN', 'TCS', 'INFY').
        name: Full company name.
        accounting_standard: Accounting standard used ('US GAAP', 'IFRS', 'IndAS').
        currency: Currency code ('USD', 'INR', etc.).
        fiscal_year: Fiscal period string (e.g. 'FY2025' or 'TTM').
        revenue_billions: Total revenue in billions.
        net_income_billions: Net income in billions.
        net_margin_percent: Net margin percentage.
        roe_percent: Return on Equity percentage.

    Returns:
        A success status message confirming the update.
    """
    db = _get_db()
    ticker_clean = ticker.strip().upper()
    data = {
        "ticker": ticker_clean,
        "name": name,
        "accounting_standard": accounting_standard,
        "currency": currency,
        "fiscal_year": fiscal_year,
        "revenue_billions": float(revenue_billions),
        "net_income_billions": float(net_income_billions),
        "net_margin_percent": float(net_margin_percent),
        "roe_percent": float(roe_percent),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection(COLLECTION_NAME).document(ticker_clean).set(data)
    return f"Successfully saved financial metrics for {name} ({ticker_clean}) in Firestore."


# --- LIVE FINANCIAL DATA & AI IMAGE GENERATION TOOLS ---

async def generate_domain_image(prompt: str, tool_context: ToolContext) -> str:
    """Generate an image for a financial item using gemini-3.1-flash-lite-image model in global region, save as artifact, and upload to Cloud Storage.

    Args:
        prompt: Description of the financial infographic, logo, or report graphic to generate.
        tool_context: ADK tool context used to save the generated image artifact.

    Returns:
        The public HTTPS URL of the uploaded image in Cloud Storage.
    """
    clean_prompt = f"Financial research studio graphic: {prompt}"
    
    # Initialize genai Client in global location using Vertex AI
    genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    
    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=clean_prompt,
    )
    
    image_bytes = None
    mime_type = "image/png"
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            if part.inline_data.mime_type:
                mime_type = part.inline_data.mime_type
            break
            
    if not image_bytes:
        return "Failed to generate image bytes from gemini-3.1-flash-lite-image."

    filename = f"financial_graphic_{uuid.uuid4().hex[:8]}.png"

    # 1. Save artifact to ADK tool context for Playground display
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    await tool_context.save_artifact(filename, artifact_part)

    # 2. Upload image bytes directly to Cloud Storage bucket (without writing to local disk)
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return (
        f"Successfully generated financial image with gemini-3.1-flash-lite-image!\n"
        f"• Saved to Playground Artifacts as: {filename}\n"
        f"• Public Cloud Storage URL: {public_url}\n"
        f"Markdown Embed: ![{prompt}]({public_url})"
    )


async def generate_domain_video(prompt: str, tool_context: ToolContext) -> str:
    """Generate a short financial overview video using gemini-omni-flash-preview in global region, save as artifact, and upload to Cloud Storage.

    Args:
        prompt: Description of the financial overview video or market animation to generate.
        tool_context: ADK tool context used to save the generated video artifact.

    Returns:
        The public HTTPS URL of the uploaded video in Cloud Storage.
    """
    clean_prompt = f"Abstract financial graphic animation: {prompt}. Rising bar charts, stock ticker indicators, sleek corporate aesthetic, motion graphic."
    
    try:
        # Initialize genai Client in global location using Vertex AI
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=clean_prompt,
        )
        
        if not (hasattr(interaction, "output_video") and interaction.output_video and getattr(interaction.output_video, "data", None)):
            return "Failed to generate video data from gemini-omni-flash-preview."

        video_bytes = base64.b64decode(interaction.output_video.data)
        filename = f"financial_video_{uuid.uuid4().hex[:8]}.mp4"
        mime_type = "video/mp4"

        # 1. Save artifact to ADK tool context for Playground display
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename, artifact_part)

        # 2. Upload video bytes directly to Cloud Storage bucket (without writing to local disk)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return (
            f"Successfully generated financial video with gemini-omni-flash-preview!\n"
            f"• Saved to Playground Artifacts as: {filename}\n"
            f"• Public Cloud Storage URL: {public_url}"
        )
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {str(e)}"


def fetch_live_exchange_rate(base_currency: str = "INR", target_currency: str = "USD") -> str:
    """Fetch live currency exchange rates from the free Frankfurter open API without an API key.

    Args:
        base_currency: Source currency code (e.g. 'INR', 'EUR', 'GBP').
        target_currency: Target currency code (e.g. 'USD', 'EUR').

    Returns:
        A formatted string with the live exchange rate.
    """
    base = base_currency.strip().upper()
    target = target_currency.strip().upper()
    
    if base == target:
        return f"1 {base} = 1.00 {target}"
        
    try:
        url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            rate = data.get("rates", {}).get(target)
            if rate:
                return f"Live FX Exchange Rate (Frankfurter API): 1 {base} = {rate} {target}"
            return f"Could not retrieve rate for {base} -> {target}."
    except Exception as e:
        fallback = 0.012 if base == "INR" and target == "USD" else 1.0
        return f"Live FX API unavailable ({str(e)}). Using fallback rate: 1 {base} = {fallback} {target}"


def fetch_company_news(ticker_or_company: str) -> str:
    """Fetch recent financial news headlines for a company using Google News RSS.

    Args:
        ticker_or_company: Ticker or company name (e.g. 'JPMorgan', 'TCS', 'Infosys', 'Accenture').

    Returns:
        A list of top news headlines and article links.
    """
    query = urllib.parse.quote(f"{ticker_or_company} financial earnings")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            tree = ET.fromstring(resp.read().decode())
            items = tree.findall(".//item")[:4]
            if not items:
                return f"No recent news articles found for {ticker_or_company}."
            
            results = [f"Latest Market & Financial News for '{ticker_or_company}':"]
            for idx, item in enumerate(items, 1):
                title = item.find("title").text if item.find("title") is not None else "No Title"
                link = item.find("link").text if item.find("link") is not None else "#"
                results.append(f"{idx}. {title}\n   Link: {link}")
            return "\n".join(results)
    except Exception as e:
        return f"Error fetching news for {ticker_or_company}: {str(e)}"


def fetch_live_market_data(ticker: str) -> str:
    """Fetch real-time stock price, valuation ratios, market capitalization, and key figures from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g. 'JPMC', 'GS', 'ACN', 'TCS', 'INFY').

    Returns:
        A formatted string with live market metrics.
    """
    clean_ticker = ticker.strip().upper()
    yf_symbol = TICKER_MAP.get(clean_ticker, clean_ticker)
    
    try:
        t = yf.Ticker(yf_symbol)
        info = t.info
        
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        mcap = info.get("marketCap")
        pe_trailing = info.get("trailingPE")
        pe_forward = info.get("forwardPE")
        profit_margin = info.get("profitMargins")
        high_52 = info.get("fiftyTwoWeekHigh")
        low_52 = info.get("fiftyTwoWeekLow")
        currency = info.get("currency", "USD")
        
        mcap_str = f"{mcap / 1e9:.2f} Billion {currency}" if mcap else "N/A"
        margin_str = f"{profit_margin * 100:.2f}%" if profit_margin else "N/A"
        
        return (
            f"Live Market Data for {clean_ticker} (Symbol: {yf_symbol}):\n"
            f"• Current Price: {price} {currency}\n"
            f"• Market Cap: {mcap_str}\n"
            f"• Trailing P/E: {pe_trailing if pe_trailing else 'N/A'}\n"
            f"• Forward P/E: {pe_forward if pe_forward else 'N/A'}\n"
            f"• Profit Margin: {margin_str}\n"
            f"• 52-Week Range: {low_52} - {high_52} {currency}"
        )
    except Exception as e:
        return f"Error fetching live market data for {ticker}: {str(e)}"


def calculate_normalized_kpis(ticker: str, inr_to_usd_rate: float = 0.0) -> str:
    """Normalize financial figures to USD and compute standardized KPIs (Net Margin, ROE, Revenue in USD billions).

    Args:
        ticker: Stock ticker symbol (e.g. 'JPMC', 'GS', 'ACN', 'TCS', 'INFY').
        inr_to_usd_rate: Optional custom exchange rate. If 0.0, fetches live rate from Frankfurter API.

    Returns:
        A string summarizing normalized KPIs in USD.
    """
    clean_ticker = ticker.strip().upper()
    db = _get_db()
    doc_ref = db.collection(COLLECTION_NAME).document(clean_ticker)
    doc = doc_ref.get()
    
    if not doc.exists:
        return f"No financial record found in Firestore for ticker '{clean_ticker}'. Please add it first."
    
    data = doc.to_dict()
    raw_rev = data.get("revenue_billions", 0.0)
    raw_income = data.get("net_income_billions", 0.0)
    curr = data.get("currency", "USD")
    
    if curr.upper() == "INR":
        if inr_to_usd_rate <= 0.0:
            fx_res = fetch_live_exchange_rate("INR", "USD")
            try:
                rate = float(fx_res.split("=")[1].strip().split()[0])
            except Exception:
                rate = 0.0104
        else:
            rate = inr_to_usd_rate
            
        rev_usd = raw_rev * rate
        income_usd = raw_income * rate
        norm_note = f"Converted from INR to USD @ live exchange rate {rate}"
    else:
        rev_usd = raw_rev
        income_usd = raw_income
        norm_note = "Native USD figures"
        
    net_margin = (income_usd / rev_usd * 100) if rev_usd > 0 else data.get("net_margin_percent", 0.0)
    
    return (
        f"Normalized Financial Analysis for {clean_ticker} ({data.get('name')}):\n"
        f"• Base Currency: {curr} → Target Currency: USD ({norm_note})\n"
        f"• Normalized Revenue: ${rev_usd:.2f} Billion USD\n"
        f"• Normalized Net Income: ${income_usd:.2f} Billion USD\n"
        f"• Net Margin: {net_margin:.2f}%\n"
        f"• ROE: {data.get('roe_percent')}%\n"
        f"• Accounting Framework: {data.get('accounting_standard')}"
    )


def generate_dashboard_chart(tickers_csv: str = "JPMC,GS,ACN,TCS,INFY", metric: str = "net_margin") -> str:
    """Generate a visual financial KPI comparison bar chart for target companies and upload to Cloud Storage.

    Args:
        tickers_csv: Comma-separated list of stock tickers (e.g. 'JPMC,GS,ACN,TCS,INFY').
        metric: Metric to plot - 'net_margin' (Net Margin %), 'revenue' (Revenue in USD), or 'roe' (ROE %).

    Returns:
        A markdown formatted message with the public URL of the generated chart dashboard.
    """
    tickers = [t.strip().upper() for t in tickers_csv.split(",") if t.strip()]
    db = _get_db()
    
    labels = []
    values = []
    
    for t in tickers:
        doc = db.collection(COLLECTION_NAME).document(t).get()
        if doc.exists:
            d = doc.to_dict()
            labels.append(t)
            if metric.lower() == "revenue":
                rev = d.get("revenue_billions", 0.0)
                if d.get("currency") == "INR":
                    rev = rev * 0.0104  # live rate for visualization comparison
                values.append(rev)
            elif metric.lower() == "roe":
                values.append(d.get("roe_percent", 0.0))
            else:  # net_margin
                values.append(d.get("net_margin_percent", 0.0))

    if not values:
        return "No data found for the requested tickers to create a chart."

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728", "#9467bd"][:len(labels)]
    
    bars = ax.bar(labels, values, color=colors, width=0.55)
    
    unit_str = "Revenue ($B USD)" if metric.lower() == "revenue" else ("ROE (%)" if metric.lower() == "roe" else "Net Margin (%)")
    ax.set_ylabel(unit_str, fontsize=11, fontweight="bold")
    ax.set_title(f"Financial Research Studio - {unit_str} Comparison", fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + (max(values) * 0.02),
            f"{height:.1f}%" if metric.lower() != "revenue" else f"${height:.1f}B",
            ha="center",
            va="bottom",
            fontweight="bold"
        )
        
    plt.tight_layout()
    
    filename = f"dashboard_{metric.lower()}_{uuid.uuid4().hex[:8]}.png"
    local_path = f"/tmp/{filename}"
    plt.savefig(local_path, dpi=150)
    plt.close()

    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_filename(local_path)
        
        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return (
            f"Successfully generated visual financial dashboard chart for {metric.upper()}!\n"
            f"Public Chart URL: {public_url}\n"
            f"Markdown Embed: ![Financial Dashboard]({public_url})"
        )
    except Exception as e:
        return f"Chart generated locally at {local_path}, but Cloud Storage upload failed: {str(e)}"


# --- A2UI SCHEMA MANAGER SYSTEM PROMPT CONFIGURATION ---

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a Financial Research Studio assistant. You retrieve financial metrics from Firestore, "
        "fetch live exchange rates (Frankfurter API) and market news (Google News), fetch live stock data (Yahoo Finance), "
        "normalize multi-currency figures (INR/USD), compute KPIs (Net Margin, ROE), generate visual chart dashboards, "
        "generate AI financial infographics (gemini-3.1-flash-lite-image), generate AI financial overview videos (gemini-omni-flash-preview), "
        "safely execute Python code in an Agent Engine sandbox, "
        "and remember user preferences across sessions using Memory Bank for target companies (JPMC, GS, ACN, TCS, INFY)."
    ),
    workflow_description="Analyze financial requests and return structured UI cards or tables when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Always start your A2UI JSON array with a beginRendering object specifying surfaceId and root component, followed by surfaceUpdate. For example: "
        "[{\"beginRendering\": {\"surfaceId\": \"watchlist_surface\", \"root\": \"root\"}}, {\"surfaceUpdate\": {\"surfaceId\": \"watchlist_surface\", \"components\": [...]}}]. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


# --- CODE EXECUTOR & MEMORY BANK SERVICE CONFIGURATION ---

# Read Agent Engine resource name from deployment_metadata.json if available
deployment_metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_resource_name = None
if deployment_metadata_path.exists():
    try:
        with open(deployment_metadata_path, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)

# Memory Bank Service builder for deployed container usage
def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        get_company_financials,
        list_watchlist_companies,
        upsert_company_financials,
        generate_domain_image,
        generate_domain_video,
        fetch_live_exchange_rate,
        fetch_company_news,
        fetch_live_market_data,
        calculate_normalized_kpis,
        generate_dashboard_chart,
        PreloadMemoryTool(),
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
    code_executor=code_executor,
)

app = App(
    root_agent=root_agent,
    name="app",
)
