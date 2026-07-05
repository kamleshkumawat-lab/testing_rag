import tiktoken
from django.conf import settings
from datetime import timedelta
from django.db.models import Count
from django.utils import timezone
from openai import OpenAI
from pgvector.django import CosineDistance
from .models import *

class TextChunkService:

    def __init__(
        self,
        chunk_size=400,
        chunk_overlap=50,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def chunk_text(self, text):

        tokens = self.encoding.encode(text)

        chunks = []

        start = 0

        while start < len(tokens):

            end = start + self.chunk_size

            chunk = self.encoding.decode(
                tokens[start:end]
            )

            chunks.append(chunk)

            start += (
                self.chunk_size
                - self.chunk_overlap
            )

        return chunks
    
class EmbeddingService:

    def __init__(self):

        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )

    def generate_embedding(self, text):

        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )

        return response.data[0].embedding
    from django.conf import settings

class RAGService:

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
        )

        self.embedding_service = EmbeddingService()

    def get_history(
        self,
        conversation,
        limit=5,
    ):

        messages = (
            ConversationMessage.objects.filter(
                conversation=conversation
            )
            .order_by("-created_at")[:limit]
        )

        return list(reversed(messages))

    def retrieve_chunks(
        self,
        question,
        top_k=5,
    ):

        query_embedding = (
            self.embedding_service.generate_embedding(
                question
            )
        )

        chunks = (
            DocumentChunk.objects.filter(
                document__status=Document.Status.COMPLETED
            )
            .annotate(
                distance=CosineDistance(
                    "embedding",
                    query_embedding,
                )
            )
            .order_by("distance")[:top_k]
        )

        return list(chunks)

    def build_prompt(
        self,
        history,
        chunks,
        question,
    ):

        history_text = "\n".join(
            f"{message.role}: {message.content}"
            for message in history
        )

        context = "\n\n".join(
            chunk.content
            for chunk in chunks
        )

        return f"""
You are an SEO assistant.

Use ONLY the supplied context to answer.

If the answer is not present in the context,
reply:

"I don't have enough information from the uploaded documents."

Conversation History:

{history_text}

Context:

{context}

Question:

{question}
"""

    def generate_answer(
        self,
        prompt,
    ):

        response = self.client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful SEO assistant."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        return response.choices[0].message.content

    def generate_response(
        self,
        conversation,
        question,
        top_k=5,
        history_limit=5,
    ):

        history = self.get_history(
            conversation=conversation,
            limit=history_limit,
        )

        chunks = self.retrieve_chunks(
            question=question,
            top_k=top_k,
        )

        if not chunks:

            answer = (
                "No processed documents are available. "
                "Please upload and process a document first."
            )

            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.Role.ASSISTANT,
                content=answer,
            )

            return {
                "answer": answer,
                "assistant_message": assistant_message,
                "sources": [],
            }

        prompt = self.build_prompt(
            history=history,
            chunks=chunks,
            question=question,
        )

        answer = self.generate_answer(
            prompt=prompt,
        )

        assistant_message = ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.ASSISTANT,
            content=answer,
            metadata={
                "source_chunk_ids": [
                    chunk.id
                    for chunk in chunks
                ]
            },
        )

        return {
            "answer": answer,
            "assistant_message": assistant_message,
            "sources": [
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document.id,
                    "document_title": chunk.document.title,
                    "content": chunk.content,
                    "distance": getattr(chunk, "distance", None),
                }
                for chunk in chunks
            ],
        }
    
    
class TextToSQLService:

    def can_handle(self, question):

        question = question.lower().strip()

        if "how many documents" not in question:
            return False

        return any(
            keyword in question
            for keyword in [
                "today",
                "day",
                "week",
                "month",
            ]
        )

    def execute(
        self,
        conversation,
        question,
    ):

        question = question.lower().strip()

        queryset = Document.objects.filter(
            created_by=conversation.user
        )

        # Today
        if "today" in question:

            total = queryset.filter(
                created_at__date=timezone.localdate()
            ).count()

            return {
                "answer": f"You uploaded {total} document(s) today.",
                "sources": [],
            }

        # Last 24 hours
        if "day" in question:

            start = timezone.now() - timedelta(days=1)

            total = queryset.filter(
                created_at__gte=start
            ).count()

            return {
                "answer": f"You uploaded {total} document(s) in the last 24 hours.",
                "sources": [],
            }

        # Last 7 days
        if "week" in question:

            start = timezone.now() - timedelta(days=7)

            total = queryset.filter(
                created_at__gte=start
            ).count()

            return {
                "answer": f"You uploaded {total} document(s) in the last 7 days.",
                "sources": [],
            }

        # Last 30 days
        if "month" in question:

            start = timezone.now() - timedelta(days=30)

            total = queryset.filter(
                created_at__gte=start
            ).count()

            return {
                "answer": f"You uploaded {total} document(s) in the last 30 days.",
                "sources": [],
            }

        return None