from pathlib import Path
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


DOCUMENT_ID = "CV-MAN-ATD-001"

DEFAULT_PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "documents"
    / "manual_atendimento_cineviva.pdf"
)


def normalize_pdf_text(text: str) -> str:
    """Normaliza o texto extraído do PDF antes da divisão em trechos."""

    text = re.sub(r"(?<!\n)(#{1,6}\s)", r"\n\1", text)
    text = re.sub(r"(?<!\n)(-\s)", r"\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def load_pdf_documents(
    pdf_path: Path | str = DEFAULT_PDF_PATH,
) -> list[Document]:
    """Lê o PDF e transforma suas páginas em documentos LangChain."""

    resolved_path = Path(pdf_path)

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"Documento não encontrado: {resolved_path}"
        )

    with resolved_path.open("rb") as pdf_file:
        if pdf_file.read(4) != b"%PDF":
            raise ValueError(
                f"O arquivo não possui um cabeçalho PDF válido: "
                f"{resolved_path}"
            )

    reader = PdfReader(str(resolved_path))
    documents = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        extracted_text = page.extract_text() or ""
        normalized_text = normalize_pdf_text(extracted_text)

        if not normalized_text:
            continue

        documents.append(
            Document(
                page_content=normalized_text,
                metadata={
                    "source": resolved_path.name,
                    "page": page_number,
                    "document_id": DOCUMENT_ID,
                },
            )
        )

    if not documents:
        raise ValueError(
            f"Nenhum texto foi extraído do documento: {resolved_path}"
        )

    return documents


def split_documents(
    documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """Divide os documentos em trechos menores e identificáveis."""

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n## ",
            "\n### ",
            "\n- ",
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    chunks = text_splitter.split_documents(documents)

    for chunk_number, chunk in enumerate(
        chunks,
        start=1,
    ):
        chunk.metadata["chunk_id"] = (
            f"CV-{chunk_number:03d}"
        )

    return chunks


def load_cinemidas_chunks(
    pdf_path: Path | str = DEFAULT_PDF_PATH,
) -> list[Document]:
    """Executa o carregamento e a divisão do manual."""

    documents = load_pdf_documents(pdf_path)
    return split_documents(documents)
