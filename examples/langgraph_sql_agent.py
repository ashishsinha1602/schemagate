"""A LangGraph text-to-SQL agent that sends the model only the tables each question needs.

    pip install langchain-schemagate langgraph langchain-anthropic tiktoken
    export ANTHROPIC_API_KEY=...
    python examples/langgraph_sql_agent.py

Four nodes: select the schema (schemagate, no model call), write one SELECT,
run it, answer from the rows. A failed query goes back to the model once with
the error. Without ANTHROPIC_API_KEY it uses a local Ollama model instead
(`pip install langchain-ollama`, `ollama pull qwen2.5:3b`); a 3B model gets
most of these wrong, which is the model, not the tables it was given.

Runs against schemagate's bundled demo database (42 tables and views, SQLite,
seeded rows), so there is nothing to configure. Swap `demo_catalog()` for
`Catalog().bootstrap("postgresql://...")` to point it at your own.
"""
import os
import sqlite3
from typing import TypedDict

import tiktoken
from langgraph.graph import END, StateGraph
from schemagate import Principal
from schemagate.demo_schema import demo_catalog
from langchain_schemagate import SchemagateRetriever, prompt_fragment

catalog = demo_catalog()
retriever = SchemagateRetriever(catalog=catalog, top_k=6,
                                principal=Principal("okta:jdoe", roles={"finance"}))
db = sqlite3.connect(catalog._demo_url[len("sqlite:///"):])
if os.environ.get("ANTHROPIC_API_KEY"):
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(model="claude-haiku-5-5", max_tokens=1024)
else:
    from langchain_ollama import ChatOllama
    llm = ChatOllama(model="qwen2.5:3b", temperature=0)
enc = tiktoken.get_encoding("cl100k_base")

# What a "dump the whole schema" agent would send on every call, rendered the same way.
FULL_SCHEMA = "\n\n".join(d.render_ddl(max_columns=10**6) for d in catalog.objects())

PROMPT = """You write one SQLite SELECT that answers the question.
Use only the tables and columns below. Reply with the SQL only, no explanation.

{schema}

Question: {question}{feedback}
SQL:"""


class State(TypedDict, total=False):
    question: str
    tables: list
    schema: str
    sql: str
    rows: list
    error: str
    tries: int
    answer: str


def select_schema(state: State) -> State:
    docs = retriever.invoke(state["question"])
    return {"schema": prompt_fragment(docs), "tries": 0,
            "tables": [f'{d.metadata["name"]} ({d.metadata["reason"]})' for d in docs]}


def write_sql(state: State) -> State:
    feedback = ""
    if state.get("error"):
        feedback = f"\n\nYour previous SQL:\n{state['sql']}\nfailed with: {state['error']}\nFix it."
    out = llm.invoke(PROMPT.format(schema=state["schema"], question=state["question"], feedback=feedback))
    sql = out.text.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return {"sql": sql, "tries": state.get("tries", 0) + 1}


def run_sql(state: State) -> State:
    if not state["sql"].lstrip().lower().startswith(("select", "with")):
        return {"error": "only SELECT is allowed", "rows": []}
    try:
        return {"rows": db.execute(state["sql"]).fetchmany(20), "error": ""}
    except sqlite3.Error as e:
        return {"error": str(e), "rows": []}


def retry_or_answer(state: State) -> str:
    return "write_sql" if state["error"] and state["tries"] < 2 else "answer"


def answer(state: State) -> State:
    if state["error"]:
        return {"answer": f"Could not answer: {state['error']}"}
    out = llm.invoke(f"Question: {state['question']}\nSQL result rows: {state['rows']}\n"
                     "Answer the question in one sentence from these rows only.")
    return {"answer": out.text.strip()}


graph = StateGraph(State)
graph.add_node("select_schema", select_schema)
graph.add_node("write_sql", write_sql)
graph.add_node("run_sql", run_sql)
graph.add_node("answer", answer)
graph.set_entry_point("select_schema")
graph.add_edge("select_schema", "write_sql")
graph.add_edge("write_sql", "run_sql")
graph.add_conditional_edges("run_sql", retry_or_answer, {"write_sql": "write_sql", "answer": "answer"})
graph.add_edge("answer", END)
agent = graph.compile()

if __name__ == "__main__":
    full = len(enc.encode(FULL_SCHEMA))
    print(f"Full schema: {len(catalog.objects())} objects, {full:,} tokens on every call\n")
    for q in ["Which customers owe us money?",
              "How many orders did each carrier ship?",
              "Which products are below their reorder level, and in which warehouse?"]:
        s = agent.invoke({"question": q})
        sent = len(enc.encode(s["schema"]))
        print(f"Q: {q}")
        print(f"   tables: {', '.join(s['tables'])}")
        print(f"   schema tokens: {sent:,} vs {full:,} ({1 - sent / full:.0%} fewer)")
        print(f"   SQL: {' '.join(s['sql'].split())}")
        print(f"   rows: {s['rows'][:5]}  tries: {s['tries']}")
        print(f"   A: {s['answer']}\n")
