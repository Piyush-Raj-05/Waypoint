from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from tools import web_search , scrape_url 
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    temperature=0
)



# 1st agent

search_system = """
You are a professional web search agent.

Rules:
1. Perform ONLY ONE web search.
2. Use one comprehensive query.
3. Return the top relevant URLs.
4. Do NOT perform another search.
5. Do NOT scrape websites.
6. Wait for the reader agent.
- Never answer the user's question.
- Never summarize.
- Use the web_search tool.
- Return at most 5 trusted URLs.
- Prefer official websites, government sites, research papers and Wikipedia.

Output format:

1. Title
   URL

2. Title
   URL

Nothing else.
"""

def build_search_agent():
    return create_agent(
        model=llm,
        tools=[web_search],
        system_prompt=search_system
    )

#2nd agent

def build_reader_agent():
    return create_agent(
        model = llm,
        tools = [scrape_url]
    )

#writer chain 

writer_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert research writer. Write clear, structured and insightful reports."),
    ("human", """Write a detailed research report on the topic below.

Topic: {topic}

Research Gathered:
{research}

Structure the report as:
- Introduction
- Key Findings (minimum 3 well-explained points)
- Conclusion
- Sources (list all URLs found in the research)

Be detailed, factual and professional."""),
])

writer_chain = writer_prompt | llm | StrOutputParser()

#critic_chain 

critic_prompt = ChatPromptTemplate.from_messages([
     ("system", "You are a sharp and constructive research critic. Be honest and specific."),
    ("human", """Review the research report below and evaluate it strictly.

Report:
{report}

Respond in this exact format:

Score: X/10

Strengths:
- ...
- ...

Areas to Improve:
- ...
- ...

One line verdict:
..."""),
])

critic_chain = critic_prompt | llm | StrOutputParser()
