from typing import List
from app.core.config import CHUNK_OVERLAP, CHUNK_SIZE


def split_text_recursively(
    text: str,
    max_chunk_size: int,
    overlap: int,
    separators: List[str] | None = None,
) -> List[str]:
    """
    Split text into chunks of at most `max_chunk_size` characters,
    prioritizing natural boundaries (paragraphs, lines, sentences).
    Includes `overlap` characters from the end of the previous chunk.
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "; ", ", ", " "]

    if len(text) <= max_chunk_size:
        cleaned = text.strip()
        return [cleaned] if cleaned else []

    # Choose first separator present in text
    sep = ""
    for s in separators:
        if s in text:
            sep = s
            break

    if not sep:
        # Hard split if no separator found
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += max_chunk_size - overlap
        return chunks

    parts = text.split(sep)
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_length = 0

    for part in parts:
        part_len = len(part) + len(sep)
        if current_length + part_len <= max_chunk_size:
            current_chunk.append(part)
            current_length += part_len
        else:
            if current_chunk:
                combined = sep.join(current_chunk).strip()
                if combined:
                    chunks.append(combined)
            # Handle part larger than max_chunk_size
            if len(part) > max_chunk_size:
                sub_chunks = split_text_recursively(
                    part, max_chunk_size, overlap, separators[1:]
                )
                chunks.extend(sub_chunks)
                current_chunk = []
                current_length = 0
            else:
                current_chunk = [part]
                current_length = len(part)

    if current_chunk:
        combined = sep.join(current_chunk).strip()
        if combined:
            chunks.append(combined)

    # If overlap is requested and chunks exist, combine with overlap if beneficial
    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks: List[str] = []
        for i, ch in enumerate(chunks):
            if i == 0:
                overlapped_chunks.append(ch)
            else:
                prev = chunks[i - 1]
                overlap_text = prev[-overlap:].strip()
                # Join overlap cleanly
                if overlap_text and not ch.startswith(overlap_text):
                    overlapped_chunks.append(f"... {overlap_text} {ch}")
                else:
                    overlapped_chunks.append(ch)
        return overlapped_chunks

    return chunks


def chunk_document(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """Generate clean, non-empty chunks from text."""
    if not text or not text.strip():
        return []
    return split_text_recursively(text, max_chunk_size=chunk_size, overlap=chunk_overlap)
