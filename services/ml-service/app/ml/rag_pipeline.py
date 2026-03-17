"""
RAG pipeline for Sudoku technique retrieval.

QdrantTechniqueRetriever wraps the Qdrant collection and exposes a
LangChain-compatible retrieve() method.  The LCEL explain chain combines
retrieval + prompt formatting + LLM call into a single Runnable.
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter

from app.config import settings
from app.ml.embeddings import embed_one

# ── Qdrant client singleton ───────────────────────────────────────────────────

_qdrant: QdrantClient | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _qdrant


# ── Retriever ─────────────────────────────────────────────────────────────────

class QdrantTechniqueRetriever:
    """Retrieve the top-k most similar techniques from Qdrant."""

    def __init__(self, top_k: int = 3):
        self.top_k = top_k

    def retrieve(
        self,
        query: str,
        *,
        difficulty_max: int | None = None,
        tags: list[str] | None = None,
    ) -> list[Document]:
        vector = embed_one(query)
        client = _get_qdrant()

        # Build optional payload filter
        must = []
        if difficulty_max is not None:
            must.append(
                {
                    "key": "difficulty_level",
                    "range": {"lte": difficulty_max},
                }
            )
        if tags:
            must.append(
                {
                    "key": "tags",
                    "match": {"any": tags},
                }
            )
        query_filter = Filter(must=must) if must else None

        results = client.search(
            collection_name=settings.TECHNIQUES_COLLECTION,
            query_vector=vector,
            limit=self.top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        docs: list[Document] = []
        for hit in results:
            payload: dict[str, Any] = hit.payload or {}
            docs.append(
                Document(
                    page_content=_format_technique(payload),
                    metadata={
                        "id": payload.get("id"),
                        "name": payload.get("name"),
                        "difficulty_level": payload.get("difficulty_level"),
                        "tags": payload.get("tags", []),
                        "score": hit.score,
                    },
                )
            )
        return docs

    # LangChain Runnable adapter
    def as_runnable(self):
        return RunnableLambda(lambda q: self.retrieve(q))


def _format_technique(p: dict[str, Any]) -> str:
    lines = [
        f"**{p.get('name', 'Unknown')}** (difficulty {p.get('difficulty_level', '?')}/5)",
        f"Concept: {p.get('concept', '')}",
        f"Method: {p.get('method', '')}",
    ]
    if p.get("visual_description"):
        lines.append(f"Visual: {p['visual_description']}")
    if p.get("prerequisite_techniques"):
        lines.append(f"Prerequisites: {', '.join(p['prerequisite_techniques'])}")
    return "\n".join(lines)


# ── LCEL explain chain ────────────────────────────────────────────────────────

_EXPLAIN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an expert Sudoku tutor. "
                "Use the retrieved technique references below to explain clearly and concisely. "
                "Always end your explanation with one follow-up question to check understanding.\n\n"
                "Retrieved techniques:\n{context}"
            ),
        ),
        ("human", "{question}"),
    ]
)


def build_explain_chain(llm: Any):
    """
    Return an LCEL chain: question → retrieve → format → llm → str.

    Input:  {"question": str}
    Output: str
    """
    retriever = QdrantTechniqueRetriever(top_k=3)

    def retrieve_and_format(inputs: dict) -> dict:
        docs = retriever.retrieve(inputs["question"])
        context = "\n\n---\n\n".join(d.page_content for d in docs)
        return {"context": context, "question": inputs["question"]}

    chain = (
        RunnableLambda(retrieve_and_format)
        | _EXPLAIN_PROMPT
        | llm
        | StrOutputParser()
    )
    return chain
