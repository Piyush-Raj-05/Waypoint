# ResearchFlow AI 🧭

### Enterprise Multi-Agent AI Research Assistant

ResearchFlow AI is a multi-agent research assistant that automates the research workflow from web discovery → source reading → report generation → quality review.

The application uses specialized AI agents to search trusted web sources, extract useful information, generate a structured research report, and evaluate the final output.

## 🚀 Live Demo

👉 https://researchflow-ai-akash.streamlit.app/

## ✨ Features

- 🔍 Search Agent — searches the web for relevant and reliable sources.
- 📖 Reader Agent — reads and extracts useful information from selected web pages.
- ✍️ Writer Agent — synthesizes the extracted information into a structured research report.
- 🧠 Critic Agent — reviews the generated report and provides a quality assessment.
- 🌐 Live Web Research — research is grounded in current web sources instead of relying only on the model's training data.
- 📄 Report Export — download generated reports as Markdown, TXT, or PDF.
- 🗂️ Session Report History — previously generated reports remain available during the current Streamlit session.
- 🎨 Custom UI — research-focused Streamlit interface with dark/light themes, metrics, agent status indicators, and expandable workflow sections.

## 🏗️ Research Workflow

User enters research topic
          │
          ▼
    🔍 Search Agent
          │
          ▼
    📖 Reader Agent
          │
          ▼
     ✍ Writer Agent
          │
          ▼
     🧠 Critic Agent
          │
          ▼
      Final Report

### Agent responsibilities

Search Agent

Finds relevant web sources for the requested topic. The UI displays the agent's completion status rather than exposing the raw internal search-tool response.

Reader Agent

Processes the selected web content and extracts the information needed by the downstream report-generation step.

Writer Agent

Uses the extracted research to produce the final structured Markdown report.

Critic Agent

Evaluates the report and returns a quality assessment that is shown separately from the generated report.

## 🖥️ User Interface

The Research page provides:

- Research topic input
- Example research topics
- Pipeline progress indicator
- Execution-time metrics
- Source count
- Report word count
- Estimated reading time
- Critic score
- Expandable Search, Reader, Writer, and Critic agent sections

### UI cleanup update

The Search Agent panel intentionally does not render the raw internal search response.

Previously, the interface could show an internal structure similar to:

**Search results**

[{'type': 'text', 'text': '...', 'extras': {...}}]

and a duplicated list of source URLs.

That raw tool output has been removed from the visible Search Agent panel.

The application now keeps the Search Agent section focused on its status, while the final generated report contains the structured source references in its dedicated Sources section.

This keeps internal agent/tool data separate from the user-facing research report.

## 📑 Generated Report

A completed report contains:

Research Report
├── Introduction
├── Key Findings
├── Conclusion
└── Sources

The report can be previewed directly in the application and exported in:

- Markdown (.md)
- Plain text (.txt)
- PDF (.pdf, when fpdf2 is available)

## 🛠️ Tech Stack

- Python
- Streamlit
- LangChain / LangGraph agent workflow
- Tavily web search
- LLM-based report generation
- fpdf2 for PDF export
- HTML/CSS customization for the Streamlit interface

## 📁 Project Structure

A typical project structure is:

ResearchFlow-AI/
│
├── app.py
├── agent.py
├── pipeline.py
├── tools.py
├── requirements.txt
├── README.md
├── .env
└── ...

### Main files

File | Responsibility
--- | ---
app.py | Streamlit UI, session state, metrics, report rendering, downloads
agent.py | Agent definitions and LLM-facing agent configuration
pipeline.py | Research workflow orchestration and state passing
tools.py | Web-search and supporting research tools
requirements.txt | Python dependencies

## ⚙️ Local Setup

### 1. Clone the repository

git clone https://github.com/akashgoswami139/ResearchFlow-AI.git
cd ResearchFlow-AI

### 2. Create a virtual environment

python -m venv .venv

Windows PowerShell:

.\.venv\Scripts\Activate.ps1

macOS/Linux:

source .venv/bin/activate

### 3. Install dependencies

pip install -r requirements.txt

### 4. Configure environment variables

Create a .env file and add the API credentials required by the project.

Example:

TAVILY_API_KEY=your_tavily_api_key
# Add your configured LLM/API key variables here

Use the exact variable names expected by the current project code.

### 5. Run the Streamlit app

streamlit run app.py

The application will be available at the local Streamlit URL shown in the terminal.

## 🔄 Deployment

The project is deployed on Streamlit Cloud:

👉 https://researchflow-ai-akash.streamlit.app/

When the Streamlit app is connected to the GitHub repository, updates to the deployed branch can trigger a new deployment.

## 🔐 Environment Variables

API keys should never be committed to GitHub.

Use:

- .env for local development
- Streamlit Secrets for deployed applications

Do not place real credentials directly inside Python source files.

## 📊 Example Output

For a topic such as:

Artificial Intelligence

ResearchFlow AI can produce a workflow similar to:

Research complete

🔍 Search Agent
Completed

📖 Reader Agent
Completed

✍ Writer Agent
Completed

🧠 Critic Agent
Completed

The generated report then contains the research content followed by a structured source list.

## 🎯 Project Goal

ResearchFlow AI is designed to reduce the repetitive work involved in web-based research by coordinating multiple specialized agents instead of relying on a single LLM call.

The goal is to make research:

- faster
- more structured
- source-aware
- easier to review
- easier to export and reuse

## 👨‍💻 Developer

Akash Goswami

AI & Machine Learning Developer

- GitHub: https://github.com/akashgoswami139
- LinkedIn: https://www.linkedin.com/in/akashgoswami-/
- X: https://x.com/akashgoswami144

## 📄 License

See the repository for the project's current license and usage terms.
