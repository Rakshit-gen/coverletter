# coverletter

Give it your resume (PDF) and a job description, get back a cover letter PDF,
named after you and the company. It researches the company first — either via
Claude's native web search or Groq's `compound` model, which both search the
web server-side — so the letter references something real about the company
instead of generic filler.

## Setup

```
pip install fpdf2
```

You also need `pdftotext` on your PATH (part of poppler — `brew install poppler`
on macOS) to read the resume PDF, and one of:

```
export ANTHROPIC_API_KEY=...   # console.anthropic.com
export GROQ_API_KEY=...        # console.groq.com
```

## Command line

```
python3 cover_letter.py --resume resume.pdf --jd jd.txt
python3 cover_letter.py --resume resume.pdf --jd-text "paste the JD here" --provider groq
```

Writes `<Name>_<Company>_Cover_Letter.pdf` into the current directory (`--out`
to change that).

## Web UI

```
python3 server.py
```

Opens on `http://localhost:8000` — upload the resume, paste the JD, pick a
provider, hit generate, the PDF downloads. Local only, no dependency beyond
`cover_letter.py` itself.

## Notes

- `--provider anthropic` (default) uses Claude's `web_search` tool and tends to
  do more thorough, multi-query research; `--provider groq` uses Groq's
  `compound` model, which is faster and often cheaper.
- Contact info (email/phone) on the letter is pulled straight from your resume
  text with a regex — it's not something the model makes up.
- If the model's response doesn't come back in the expected format, the script
  fails loudly with the raw response rather than silently producing a bad PDF.
