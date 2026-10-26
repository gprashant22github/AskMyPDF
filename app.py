import os
import re
from dataclasses import dataclass

import pymupdf
import streamlit as st
from dotenv import load_dotenv
from sarvamai import SarvamAI


MODEL = "sarvam-105b-conversations"
MAX_PASSAGES = 5
CHUNK_SIZE = 900
MAX_CONTEXT_CHARS = 9000
SUMMARY_TERMS = {
    "summarize",
    "summarise",
    "summary",
    "overview",
    "takeaways",
    "takeaway",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class Passage:
    page_number: int
    text: str
    score: float


def chunk_page(page: PageText) -> list[Passage]:
    words = page.text.split()
    chunks: list[Passage] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        word_length = len(word) + (1 if current else 0)
        if current and current_length + word_length > CHUNK_SIZE:
            chunks.append(Passage(page.page_number, " ".join(current), 0.0))
            current = []
            current_length = 0
        current.append(word)
        current_length += word_length
    if current:
        chunks.append(Passage(page.page_number, " ".join(current), 0.0))
    return chunks


def all_chunks(pages: list[PageText]) -> list[Passage]:
    return [chunk for page in pages if page.text for chunk in chunk_page(page)]


def is_summary_request(question: str) -> bool:
    terms = set(tokenize(question))
    return bool(terms & SUMMARY_TERMS) or (
        "key" in terms and "points" in terms
    )


def representative_passages(chunks: list[Passage]) -> list[Passage]:
    if len(chunks) <= MAX_PASSAGES:
        return chunks
    positions = [
        round(index * (len(chunks) - 1) / (MAX_PASSAGES - 1))
        for index in range(MAX_PASSAGES)
    ]
    return [chunks[position] for position in positions]


def extract_pages(pdf_bytes: bytes) -> list[PageText]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        return [
            PageText(page_number=index + 1, text=page.get_text("text").strip())
            for index, page in enumerate(document)
        ]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def retrieve_passages(pages: list[PageText], question: str) -> list[Passage]:
    chunks = all_chunks(pages)
    if not chunks or not tokenize(question):
        return []

    if is_summary_request(question):
        return representative_passages(chunks)

    question_terms = set(tokenize(question))
    scored = []
    for chunk in chunks:
        chunk_terms = set(tokenize(chunk.text))
        overlap = len(question_terms & chunk_terms)
        phrase_bonus = 2 if question.lower() in chunk.text.lower() else 0
        if overlap or phrase_bonus:
            scored.append(
                Passage(
                    page_number=chunk.page_number,
                    text=chunk.text,
                    score=overlap / len(question_terms) + phrase_bonus,
                )
            )

    if not scored:
        return representative_passages(chunks)
    return sorted(scored, key=lambda passage: passage.score, reverse=True)[:MAX_PASSAGES]


def build_context(passages: list[Passage]) -> str:
    context_parts: list[str] = []
    total_chars = 0
    for passage in passages:
        labeled = f"[Page {passage.page_number}]\n{passage.text}"
        if total_chars + len(labeled) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(labeled)
        total_chars += len(labeled)
    return "\n\n".join(context_parts)


def answer_question(question: str, passages: list[Passage], api_key: str) -> str:
    context = build_context(passages)
    prompt = f"""Answer the question using only the supplied document passages.
For a summary request, summarize only the supplied passages and identify the
supporting pages. If the answer is not supported by the passages, say exactly:
"The answer is not in the document." Include citations such as [Page 2] for every
factual claim. Do not use outside knowledge or infer missing facts.

Document passages:
{context}

Question: {question}
"""
    client = SarvamAI(api_subscription_key=api_key)
    response = client.chat.completions(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You answer questions from provided document excerpts only.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def safe_error(error: Exception, api_key: str) -> str:
    message = str(error).replace(api_key, "[redacted]")
    status_code = getattr(error, "status_code", None)
    if status_code == 403:
        return "The Sarvam API key was rejected. Check SARVAM_API_KEY in .env."
    if status_code == 429:
        return "Sarvam rate limit or credits were reached. Try again later."
    if status_code in (400, 422):
        return "Sarvam rejected the request. The document context may be invalid."
    if status_code == 413:
        return "The selected document context is too large. Try a shorter PDF."
    if status_code in (500, 503):
        return "Sarvam is temporarily unavailable. Try again shortly."
    return f"{type(error).__name__}: {message}"


def render_page_text(pages: list[PageText]) -> None:
    st.subheader("Extracted text")
    for page in pages:
        with st.expander(f"Page {page.page_number}"):
            st.text(page.text or "(No selectable text on this page.)")


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="AskMyPDF", page_icon="📄", layout="wide")
    st.title("AskMyPDF")
    st.caption("Upload a text-based PDF and ask questions grounded in its contents.")

    uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
    if not uploaded_file:
        st.info("Upload a PDF to get started.")
        return

    try:
        pages = extract_pages(uploaded_file.getvalue())
    except (pymupdf.FileDataError, ValueError, RuntimeError) as error:
        st.error(f"Could not read this PDF: {error}")
        return

    non_empty_pages = [page for page in pages if page.text]
    word_count = sum(len(tokenize(page.text)) for page in pages)
    stats = st.columns(3)
    stats[0].metric("Pages", len(pages))
    stats[1].metric("Pages with text", len(non_empty_pages))
    stats[2].metric("Words", word_count)

    if not non_empty_pages:
        st.warning(
            "This PDF has no selectable text. It may be scanned or image-only; "
            "OCR is not included in this MVP."
        )
        render_page_text(pages)
        return

    render_page_text(pages)
    st.divider()
    st.subheader("Ask a question")
    summary_requested = st.button("Summarize PDF", type="primary")
    question = st.chat_input("What would you like to know about this document?")
    if summary_requested:
        question = "Summarize this PDF and provide the key takeaways."
    if not question:
        return

    st.chat_message("user").write(question)
    passages = retrieve_passages(pages, question)
    if not passages:
        st.chat_message("assistant").write(
            "I could not find a relevant passage in the document, so the answer is not in the document."
        )
        return

    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    if not api_key:
        st.error("SARVAM_API_KEY is missing. Add it to the local .env file before asking a question.")
        return

    with st.chat_message("assistant"):
        with st.spinner("Searching the document and generating an answer..."):
            try:
                answer = answer_question(question, passages, api_key)
            except Exception as error:
                st.error(f"Sarvam could not generate an answer: {safe_error(error, api_key)}")
                return
        st.write(answer)
        cited_pages = ", ".join(
            dict.fromkeys(f"[Page {passage.page_number}]" for passage in passages)
        )
        st.caption(f"Retrieved passages: {cited_pages}")
        with st.expander("Supporting excerpts used"):
            for passage in passages:
                st.markdown(f"**Page {passage.page_number}**")
                st.write(passage.text)


if __name__ == "__main__":
    main()
