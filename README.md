# AskMyPDF

Ask questions about a text-based PDF using local passage retrieval and Sarvam AI.
The app also supports a one-click document summary with page citations.

## Windows setup

Open PowerShell in this folder and activate the existing virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run the app with the virtual-environment
interpreter directly instead.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Make sure `.env` contains your key:

```text
SARVAM_API_KEY=your-key-here
```

Do not commit `.env`.

For a safe template, copy `.env.example` to `.env` and add your own key:

```powershell
Copy-Item .env.example .env
```

## Run locally

```powershell
streamlit run app.py
```

Then open the local URL shown by Streamlit, usually
`http://localhost:8501`.

AskMyPDF supports selectable-text PDFs. Scanned or image-only PDFs are detected
and reported, but OCR is intentionally outside this MVP.

## Testing

Run local checks without making a Sarvam API request:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py
```

The app uses lightweight in-memory chunk retrieval. Summary requests select
representative chunks from across the document; factual questions select chunks
with matching terms and retain their original PDF page numbers. Sarvam receives
only the bounded, page-labeled excerpts shown in the supporting-excerpts section.

## Streamlit Community Cloud

1. Push `app.py`, `requirements.txt`, `README.md`, `.env.example`, and `.gitignore`
   to a GitHub repository.
2. Do not commit `.env` or `.venv/`.
3. Create a new app at [Streamlit Community Cloud](https://share.streamlit.io).
4. Select the repository, branch, and `app.py` as the main file.
5. In Advanced settings, add this secret:

   ```toml
   SARVAM_API_KEY = "your-key"
   ```

6. Deploy and test the generated URL with a small selectable-text PDF.
