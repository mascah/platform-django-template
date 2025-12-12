LangChain & LangGraph Integration
==================================

Build LLM-powered processes and agent workflows in your Django modular monolith.

.. index:: langchain, langgraph, llm, agents, ai, workflows, rag

Overview
--------

`LangChain <https://python.langchain.com/>`_ is a framework for building applications powered by large language models (LLMs). `LangGraph <https://langchain-ai.github.io/langgraph/>`_ extends LangChain with graph-based orchestration for complex, stateful agent workflows.

These tools fit naturally into the modular monolith architecture:

- **LangChain chains** become services that encapsulate LLM interactions
- **LangGraph agents** handle multi-step workflows with state management
- **RAG pipelines** provide domain-specific knowledge retrieval

Common use cases:

- Chatbots and conversational interfaces
- Document Q&A with retrieval-augmented generation (RAG)
- Autonomous agents that use tools and APIs
- Multi-step workflows (research, analysis, content generation)

Architecture Patterns
---------------------

LLM components integrate with the existing services/selectors pattern. There are three approaches, depending on scope:

Dedicated AI Module
^^^^^^^^^^^^^^^^^^^

For shared LLM infrastructure, create a central ``ai`` module:

.. code-block:: text

    {project_slug}/
    ├── users/
    ├── orders/
    └── ai/                    # Shared LLM infrastructure
        ├── __init__.py
        ├── models.py          # Conversation, Message, Embedding models
        ├── services.py        # Chain and agent services
        ├── selectors.py       # Conversation history queries
        └── clients.py         # LLM client configuration

This module owns:

- LLM client initialization and configuration
- Shared prompt templates
- Conversation/message persistence
- Common chains (summarization, classification)

Per-Module Agents
^^^^^^^^^^^^^^^^^

Domain-specific agents live within their respective modules:

.. code-block:: text

    {project_slug}/orders/
    ├── models.py
    ├── services.py
    ├── selectors.py
    └── agents/                # Order-specific agents
        ├── __init__.py
        ├── support_agent.py   # Customer support agent
        └── analysis_agent.py  # Order analytics agent

This keeps domain knowledge close to the data it operates on.

Hybrid Approach
^^^^^^^^^^^^^^^

Most projects use both:

- Shared ``ai`` module for infrastructure and common chains
- Per-module agents for domain-specific workflows

Installation & Setup
--------------------

Add dependencies to ``pyproject.toml``:

.. code-block:: toml

    [project]
    dependencies = [
        # ... existing deps
        "langchain>=0.3",
        "langchain-openai>=0.2",
        "langgraph>=0.2",
    ]

Add environment variables to ``.env``:

.. code-block:: bash

    # OpenAI
    OPENAI_API_KEY=sk-...

    # Optional: LangSmith for tracing
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=lsv2_...

Create settings in ``config/settings/base.py``:

.. code-block:: python

    # LLM Configuration
    OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
    OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o-mini")

    # LangSmith (optional)
    LANGCHAIN_TRACING_V2 = env.bool("LANGCHAIN_TRACING_V2", default=False)

Initialize the LLM client in your AI module:

.. code-block:: python

    # {project_slug}/ai/clients.py
    from django.conf import settings
    from langchain_openai import ChatOpenAI

    def get_llm(
        model: str | None = None,
        temperature: float = 0.7,
    ) -> ChatOpenAI:
        """Get configured LLM client."""
        return ChatOpenAI(
            model=model or settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )

Building Your First Chain
-------------------------

Chains are sequences of LLM calls with prompt templates. Implement them as services:

.. code-block:: python

    # {project_slug}/ai/services.py
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    from .clients import get_llm

    def summarize_text(*, text: str, max_words: int = 100) -> str:
        """Summarize text using LLM.

        Args:
            text: The text to summarize.
            max_words: Maximum words in summary.

        Returns:
            Summarized text.

        Raises:
            ValueError: If text is empty.
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that summarizes text concisely."),
            ("user", "Summarize the following in {max_words} words or less:\n\n{text}"),
        ])

        chain = prompt | get_llm(temperature=0.3) | StrOutputParser()

        return chain.invoke({"text": text, "max_words": max_words})


    def classify_intent(*, message: str, categories: list[str]) -> str:
        """Classify user message into one of the given categories."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Classify the user message into exactly one category. "
                       "Respond with only the category name."),
            ("user", "Categories: {categories}\n\nMessage: {message}"),
        ])

        chain = prompt | get_llm(temperature=0) | StrOutputParser()

        return chain.invoke({
            "message": message,
            "categories": ", ".join(categories),
        })

Use these services from views or other services:

.. code-block:: python

    # In a DRF view
    from {project_slug}.ai.services import summarize_text

    class SummarizeView(APIView):
        def post(self, request):
            serializer = SummarizeInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            summary = summarize_text(
                text=serializer.validated_data["text"],
                max_words=serializer.validated_data.get("max_words", 100),
            )

            return Response({"summary": summary})

LangGraph for Agent Workflows
-----------------------------

LangGraph enables complex, stateful workflows using a graph-based approach. Agents can make decisions, use tools, and maintain state across steps.

State Definition
^^^^^^^^^^^^^^^^

Define the state your agent will track:

.. code-block:: python

    # {project_slug}/orders/agents/support_agent.py
    from typing import Annotated, TypedDict

    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

    class SupportState(TypedDict):
        """State for customer support agent."""
        messages: Annotated[list[BaseMessage], add_messages]
        order_id: int | None
        intent: str | None
        resolved: bool

Node Functions
^^^^^^^^^^^^^^

Each node is a function that takes state and returns updates:

.. code-block:: python

    from {project_slug}.ai.clients import get_llm
    from {project_slug}.orders.selectors import order_get

    def classify_intent_node(state: SupportState) -> dict:
        """Classify the customer's intent."""
        last_message = state["messages"][-1].content

        llm = get_llm(temperature=0)
        response = llm.invoke([
            {"role": "system", "content": "Classify intent as: order_status, refund, general"},
            {"role": "user", "content": last_message},
        ])

        return {"intent": response.content.strip().lower()}


    def lookup_order_node(state: SupportState) -> dict:
        """Look up order details."""
        order_id = state.get("order_id")
        if not order_id:
            return {"messages": [AIMessage(content="I need your order ID to help you.")]}

        order = order_get(order_id=order_id)
        if not order:
            return {"messages": [AIMessage(content="I couldn't find that order.")]}

        return {
            "messages": [AIMessage(
                content=f"Order #{order.id}: Status is {order.status}. "
                        f"Placed on {order.created_at.date()}."
            )]
        }


    def generate_response_node(state: SupportState) -> dict:
        """Generate a helpful response based on context."""
        llm = get_llm()

        system_prompt = """You are a helpful customer support agent.
        Be concise and friendly. If you can't help, offer to escalate."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            *[{"role": m.type, "content": m.content} for m in state["messages"]],
        ])

        return {"messages": [response], "resolved": True}

Graph Construction
^^^^^^^^^^^^^^^^^^

Wire nodes together with conditional edges:

.. code-block:: python

    def route_by_intent(state: SupportState) -> str:
        """Route to appropriate node based on intent."""
        intent = state.get("intent", "general")
        if intent == "order_status":
            return "lookup_order"
        return "generate_response"


    def build_support_agent():
        """Build and compile the support agent graph."""
        graph = StateGraph(SupportState)

        # Add nodes
        graph.add_node("classify_intent", classify_intent_node)
        graph.add_node("lookup_order", lookup_order_node)
        graph.add_node("generate_response", generate_response_node)

        # Add edges
        graph.add_edge(START, "classify_intent")
        graph.add_conditional_edges(
            "classify_intent",
            route_by_intent,
            {"lookup_order": "lookup_order", "generate_response": "generate_response"},
        )
        graph.add_edge("lookup_order", "generate_response")
        graph.add_edge("generate_response", END)

        return graph.compile()


    # Service function to run the agent
    def run_support_agent(*, message: str, order_id: int | None = None) -> str:
        """Run the support agent and return response."""
        agent = build_support_agent()

        initial_state = {
            "messages": [HumanMessage(content=message)],
            "order_id": order_id,
            "intent": None,
            "resolved": False,
        }

        result = agent.invoke(initial_state)
        return result["messages"][-1].content

RAG (Retrieval Augmented Generation)
------------------------------------

RAG enhances LLM responses with relevant documents from your knowledge base.

Core Concepts
^^^^^^^^^^^^^

1. **Document Loading**: Parse documents (PDFs, web pages, databases)
2. **Chunking**: Split documents into smaller pieces
3. **Embedding**: Convert chunks to vectors
4. **Retrieval**: Find relevant chunks for a query
5. **Generation**: Use retrieved context to generate answers

Building a RAG Service
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # {project_slug}/ai/services.py
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough
    from langchain_openai import OpenAIEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    from .clients import get_llm

    def create_embeddings():
        """Create embeddings model."""
        return OpenAIEmbeddings(model="text-embedding-3-small")


    def chunk_documents(documents: list[str], chunk_size: int = 1000) -> list[str]:
        """Split documents into chunks for embedding."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=200,
        )
        chunks = []
        for doc in documents:
            chunks.extend(splitter.split_text(doc))
        return chunks


    class RAGService:
        """Service for retrieval-augmented generation."""

        def __init__(self, vector_store):
            """Initialize with a vector store.

            Args:
                vector_store: Any LangChain-compatible vector store
                    (Chroma, Pinecone, pgvector, FAISS, etc.)
            """
            self.vector_store = vector_store
            self.retriever = vector_store.as_retriever(search_kwargs={"k": 4})

        def query(self, question: str) -> str:
            """Answer a question using RAG."""
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Answer based on the context. If unsure, say so.\n\n"
                           "Context:\n{context}"),
                ("user", "{question}"),
            ])

            def format_docs(docs):
                return "\n\n".join(doc.page_content for doc in docs)

            chain = (
                {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
                | prompt
                | get_llm(temperature=0.3)
                | StrOutputParser()
            )

            return chain.invoke(question)

        def add_documents(self, documents: list[str]) -> None:
            """Add documents to the knowledge base."""
            chunks = chunk_documents(documents)
            self.vector_store.add_texts(chunks)

Vector Store Options
^^^^^^^^^^^^^^^^^^^^

LangChain supports many vector stores. Choose based on your needs:

- **FAISS**: In-memory, good for development and small datasets
- **Chroma**: Lightweight, persistent, good for prototyping
- **pgvector**: PostgreSQL extension, keeps data in your existing database
- **Pinecone/Weaviate**: Managed services for production scale

Example with FAISS (development):

.. code-block:: python

    from langchain_community.vectorstores import FAISS

    # Create vector store
    embeddings = create_embeddings()
    vector_store = FAISS.from_texts(
        ["Your documents here..."],
        embeddings,
    )

    # Use RAG service
    rag = RAGService(vector_store)
    answer = rag.query("What is the return policy?")

Integration Patterns
--------------------

With DRF
^^^^^^^^

Create API endpoints for LLM interactions:

.. code-block:: python

    # {project_slug}/ai/apis.py
    from rest_framework.views import APIView
    from rest_framework.response import Response
    from rest_framework import serializers

    from .services import summarize_text, classify_intent

    class ChatInputSerializer(serializers.Serializer):
        message = serializers.CharField(max_length=4000)
        order_id = serializers.IntegerField(required=False)

    class ChatView(APIView):
        def post(self, request):
            serializer = ChatInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            from {project_slug}.orders.agents.support_agent import run_support_agent

            response = run_support_agent(
                message=serializer.validated_data["message"],
                order_id=serializer.validated_data.get("order_id"),
            )

            return Response({"response": response})

With Celery
^^^^^^^^^^^

Run LLM tasks asynchronously for better user experience:

.. code-block:: python

    # {project_slug}/ai/tasks.py
    from celery import shared_task

    from .services import summarize_text

    @shared_task
    def summarize_document_task(document_id: int) -> str:
        """Summarize a document asynchronously."""
        from {project_slug}.documents.selectors import document_get

        document = document_get(document_id=document_id)
        summary = summarize_text(text=document.content)

        # Store result
        from {project_slug}.documents.services import document_update
        document_update(document_id=document_id, summary=summary)

        return summary

    # Usage
    summarize_document_task.delay(document_id=123)

With Event Bus
^^^^^^^^^^^^^^

Publish events from agent actions for cross-module communication. First, define the event class (see :doc:`event-driven-architecture` for the full pattern):

.. code-block:: python

    # {project_slug}/domain_events/events.py
    from {project_slug}.domain_events.base import DomainEvent


    class FeedbackAnalyzedEvent(DomainEvent):
        """Emitted when AI analyzes customer feedback."""

        def __init__(self, feedback_id: int, sentiment: str):
            self.feedback_id = feedback_id
            self.sentiment = sentiment

Then publish the event from your service:

.. code-block:: python

    # {project_slug}/ai/services.py
    from {project_slug}.domain_events.bus import event_bus
    from {project_slug}.domain_events.events import FeedbackAnalyzedEvent

    def analyze_feedback(*, feedback_id: int) -> dict:
        """Analyze customer feedback using LLM."""
        from {project_slug}.feedback.selectors import feedback_get

        feedback = feedback_get(feedback_id=feedback_id)
        sentiment = classify_intent(
            message=feedback.content,
            categories=["positive", "neutral", "negative"],
        )

        # Publish event for other modules
        event_bus.publish(FeedbackAnalyzedEvent(
            feedback_id=feedback_id,
            sentiment=sentiment,
        ))

        return {"sentiment": sentiment}

With Django ORM
^^^^^^^^^^^^^^^

Persist conversations and agent state:

.. code-block:: python

    # {project_slug}/ai/models.py
    from django.db import models
    from django.conf import settings

    class Conversation(models.Model):
        user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
        created_at = models.DateTimeField(auto_now_add=True)
        metadata = models.JSONField(default=dict)

    class Message(models.Model):
        conversation = models.ForeignKey(
            Conversation, on_delete=models.CASCADE, related_name="messages"
        )
        role = models.CharField(max_length=20)  # user, assistant, system
        content = models.TextField()
        created_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            ordering = ["created_at"]

    # Service to persist conversation
    def conversation_add_message(
        *,
        conversation_id: int,
        role: str,
        content: str,
    ) -> Message:
        """Add a message to a conversation."""
        return Message.objects.create(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )

Streaming Responses
-------------------

For chat interfaces, stream responses token-by-token:

Django StreamingHttpResponse
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # {project_slug}/ai/apis.py
    from django.http import StreamingHttpResponse

    from .clients import get_llm

    def stream_chat(request):
        """Stream LLM response."""
        message = request.POST.get("message", "")

        def generate():
            llm = get_llm()
            for chunk in llm.stream(message):
                yield f"data: {chunk.content}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingHttpResponse(
            generate(),
            content_type="text/event-stream",
        )

Server-Sent Events with Async Views
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For async Django (``use_async=y``):

.. code-block:: python

    # {project_slug}/ai/apis.py
    from django.http import StreamingHttpResponse

    from .clients import get_llm

    async def stream_chat_async(request):
        """Stream LLM response asynchronously."""
        message = request.POST.get("message", "")

        async def generate():
            llm = get_llm()
            async for chunk in llm.astream(message):
                yield f"data: {chunk.content}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingHttpResponse(
            generate(),
            content_type="text/event-stream",
        )

Frontend Integration
^^^^^^^^^^^^^^^^^^^^

Consume the stream in your React frontend:

.. code-block:: typescript

    // apps/{project_slug}/src/hooks/useChat.ts
    export function useChat() {
      const [response, setResponse] = useState("");

      const sendMessage = async (message: string) => {
        setResponse("");

        const response = await fetch("/api/chat/stream/", {
          method: "POST",
          body: new FormData().append("message", message),
        });

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader!.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ") && line !== "data: [DONE]") {
              setResponse((prev) => prev + line.slice(6));
            }
          }
        }
      };

      return { response, sendMessage };
    }

Testing Agents
--------------

Test LLM services by mocking the LLM client:

Mocking LLM Responses
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # tests/test_ai_services.py
    import pytest
    from unittest.mock import patch, MagicMock

    from {project_slug}.ai.services import summarize_text, classify_intent

    @pytest.fixture
    def mock_llm():
        """Mock LLM client."""
        with patch("{project_slug}.ai.clients.get_llm") as mock:
            llm = MagicMock()
            mock.return_value = llm
            yield llm

    def test_summarize_text(mock_llm):
        # Arrange
        mock_llm.__or__ = lambda self, other: other  # Handle pipe operator
        mock_response = MagicMock()
        mock_response.content = "This is a summary."

        # Mock the chain invoke
        with patch("{project_slug}.ai.services.StrOutputParser") as mock_parser:
            mock_parser.return_value.invoke.return_value = "This is a summary."

            # Act
            result = summarize_text(text="Long text here...")

        # Assert
        assert "summary" in result.lower()

    def test_classify_intent(mock_llm):
        mock_response = MagicMock()
        mock_response.content = "order_status"
        mock_llm.invoke.return_value = mock_response

        result = classify_intent(
            message="Where is my order?",
            categories=["order_status", "refund", "general"],
        )

        assert result == "order_status"

Testing LangGraph Agents
^^^^^^^^^^^^^^^^^^^^^^^^

Test agent workflows by mocking individual nodes:

.. code-block:: python

    def test_support_agent_routes_to_order_lookup(mock_llm):
        """Test that order queries route to lookup node."""
        from {project_slug}.orders.agents.support_agent import build_support_agent

        # Mock intent classification
        mock_llm.invoke.return_value = MagicMock(content="order_status")

        agent = build_support_agent()
        result = agent.invoke({
            "messages": [HumanMessage(content="Where is order 123?")],
            "order_id": 123,
            "intent": None,
            "resolved": False,
        })

        # Verify order was looked up
        assert "order" in result["messages"][-1].content.lower()

Using LangSmith
^^^^^^^^^^^^^^^

Enable LangSmith for debugging in tests:

.. code-block:: python

    # conftest.py
    import os

    @pytest.fixture(autouse=True)
    def enable_langsmith_tracing():
        """Enable LangSmith tracing for debugging."""
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        yield
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

Production Considerations
-------------------------

Rate Limiting
^^^^^^^^^^^^^

Protect against abuse and control costs:

.. code-block:: python

    from django.core.cache import cache
    from rest_framework.exceptions import Throttled

    def check_rate_limit(user_id: int, limit: int = 100) -> None:
        """Check if user has exceeded rate limit."""
        key = f"llm_rate_limit:{user_id}"
        count = cache.get(key, 0)

        if count >= limit:
            raise Throttled(detail="LLM rate limit exceeded")

        cache.set(key, count + 1, timeout=3600)  # Reset hourly

Cost Tracking
^^^^^^^^^^^^^

Track token usage for billing and optimization:

.. code-block:: python

    from langchain_core.callbacks import BaseCallbackHandler

    class CostTracker(BaseCallbackHandler):
        """Track LLM token usage and costs."""

        def on_llm_end(self, response, **kwargs):
            usage = response.llm_output.get("token_usage", {})
            # Log or store usage
            logger.info(
                "LLM usage",
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )

    # Use with LLM
    llm = get_llm(callbacks=[CostTracker()])

Caching
^^^^^^^

Cache deterministic responses:

.. code-block:: python

    from django.core.cache import cache
    import hashlib

    def cached_classify(message: str, categories: list[str]) -> str:
        """Classify with caching for repeated queries."""
        cache_key = hashlib.md5(
            f"{message}:{sorted(categories)}".encode()
        ).hexdigest()

        result = cache.get(cache_key)
        if result:
            return result

        result = classify_intent(message=message, categories=categories)
        cache.set(cache_key, result, timeout=3600)
        return result

Error Handling
^^^^^^^^^^^^^^

Handle LLM failures gracefully:

.. code-block:: python

    from langchain_core.exceptions import OutputParserException
    from openai import RateLimitError, APIError

    def safe_summarize(text: str) -> str | None:
        """Summarize with graceful error handling."""
        try:
            return summarize_text(text=text)
        except RateLimitError:
            logger.warning("OpenAI rate limit hit, retrying...")
            time.sleep(60)
            return summarize_text(text=text)
        except APIError as e:
            logger.error("OpenAI API error", error=str(e))
            return None
        except OutputParserException:
            logger.warning("Failed to parse LLM output")
            return None

Common Patterns
---------------

Quick reference for common LLM patterns:

.. list-table::
   :header-rows: 1
   :widths: 20 40 20 20

   * - Pattern
     - Use Case
     - Complexity
     - Example
   * - Simple Chain
     - Text generation, summarization, classification
     - Low
     - ``summarize_text()``
   * - RAG Chain
     - Knowledge-base Q&A, document search
     - Medium
     - ``RAGService.query()``
   * - ReAct Agent
     - Tool-using assistant, API integration
     - Medium
     - Support agent with order lookup
   * - Multi-Agent
     - Complex workflows, research, analysis
     - High
     - Orchestrated specialist agents

See Also
--------

- `LangChain Documentation <https://python.langchain.com/>`_ — Official LangChain docs
- `LangGraph Documentation <https://langchain-ai.github.io/langgraph/>`_ — Official LangGraph docs
- `LangSmith <https://smith.langchain.com/>`_ — Tracing and debugging platform
- :doc:`service-layer-patterns` — Where LLM services fit in the architecture
- :doc:`event-driven-architecture` — Publishing events from agent actions
- :doc:`testing` — Testing patterns for Django
- :doc:`adding-modules` — Creating a dedicated AI module
- :doc:`../5-ai-development/claude-code` — AI-assisted development workflow
