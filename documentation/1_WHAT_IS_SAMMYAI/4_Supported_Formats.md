# Supported Text Formats

SammyAI is designed to handle various text-based formats for creative writing and research. This document outlines the supported file formats across different features of the application.

## 1. Text Editor (Editing & Viewing)

The primary interface of SammyAI is a plain-text editor tailored for writing and basic formatting.

- **Primary Format:** `.txt` (Plain Text)
- **Capabilities:**
    - Full support for opening, editing, and saving `.txt` files.
    - Uses UTF-8 encoding by default (with fallback support for Latin-1).
- **Other Formats:** 
    - While the "All Files" option allows selecting other extensions, the editor treats all inputs as plain text. Binary files (like `.docx` or `.rtf`) will not render correctly in the editor and should be converted to `.txt` first.

## 2. Context Injection (CIN)

Context Injection is a lightweight way to provide the LLM with immediate context from external files without the need for indexing.

- **Supported Formats:**
    - `.txt` (Plain Text)
    - `.pdf` (Portable Document Format)
- **Size Limit:** **50 KB**
    - CIN is optimized for smaller files (e.g., character sheets, plot outlines, or short articles).
- **Processing:**
    - For PDF files, SammyAI uses the `pdftotext` utility to extract text content before sending it to the assistant.
    - Content is injected directly into the conversation's context window.

## 3. Retrieval-Augmented Generation (RAG)

The RAG system is used for managing large volumes of information across many documents or very large files.

- **Supported Formats:**
    - `.txt` (Plain Text)
    - `.pdf` (Portable Document Format)
- **Size Limits:**
    - **Soft Limit:** Files larger than **500 KB** will trigger a warning. Indexing very large files can temporarily impact UI responsiveness.
    - **Hard Limit:** The indexer supports files up to **50 MB**.
- **Processing:**
    - **Chunking:** Documents are split into overlapping blocks (approx. 300 characters) to ensure the AI can retrieve specific, relevant sections without losing context.
    - **PDF Extraction:** Like CIN, RAG uses `pdftotext` for reliable text extraction from PDF documents.
- **Capacity:**
    - The RAG system is configured to handle up to **1,000,000 document chunks**, allowing for a vast library of research materials and stories.

---

> [!NOTE]
> **Alpha Release Notice**
> SammyAI is currently in **Alpha**. While we focus on `.txt` and `.pdf` for stability and clarity, support for additional file extensions *may* be added in future updates as the platform evolves.

> [!TIP]
> **Why only `.txt` and `.pdf`?**
> SammyAI focuses on creative writing. Plain text provides the highest level of compatibility with LLMs, while PDF support allows you to easily import scripts and exported documents without manual conversion.
