"""Local LLM queries of CalculiX / Abaqus .inp and Radioss .rad decks and of reference documents.

decks.py    open decks by alias and query them through drawgen.inpinfo, inpquery and inptext
docindex.py keyword index (SQLite FTS5, BM25) of the PDF, Markdown and text files in llm/refdocs/
tools.py    tool definitions (OpenAI function format) and their dispatch
chat.py     console chat with a model served by Ollama or llama.cpp (OpenAI-compatible API)
"""
