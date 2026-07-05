import logging

from celery import shared_task

from .models import Document, DocumentChunk
from .services import TextChunkService, EmbeddingService

logger = logging.getLogger("celery_tasks")


@shared_task
def test_task():
    logger.info("Celery is working!")
    return "Celery is working!"


@shared_task(bind=True, max_retries=3)
def process_document(self, document_id):

    document = None

    try:
        document = Document.objects.get(pk=document_id)

        document.status = Document.Status.PROCESSING
        document.save(update_fields=["status"])

        # Remove old chunks if document is reprocessed
        DocumentChunk.objects.filter(document=document).delete()

        chunk_service = TextChunkService()
        embedding_service = EmbeddingService()

        chunks = chunk_service.chunk_text(document.raw_text)

        chunk_objects = []

        for index, chunk in enumerate(chunks):

            embedding = embedding_service.generate_embedding(chunk)

            chunk_objects.append(
                DocumentChunk(
                    document=document,
                    chunk_index=index,
                    content=chunk,
                    embedding=embedding,
                )
            )

        DocumentChunk.objects.bulk_create(chunk_objects)

        document.status = Document.Status.COMPLETED
        document.save(update_fields=["status"])

        logger.info(
            "Document %s processed successfully.",
            document.id,
        )

    except Exception as exc:

        logger.exception(
            "Error processing document %s",
            document_id,
        )

        if document:
            document.status = Document.Status.FAILED
            document.save(update_fields=["status"])

        raise self.retry(exc=exc, countdown=10)