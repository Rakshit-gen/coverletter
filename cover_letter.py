#!/usr/bin/env python3
"""Generate a tailored cover letter PDF from a resume PDF and a job description.

Usage:
    export ANTHROPIC_API_KEY=...   # or GROQ_API_KEY=... with --provider groq
    python3 cover_letter.py --resume resume.pdf --jd jd.txt
    python3 cover_letter.py --resume resume.pdf --jd-text "paste the JD here" --provider groq
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date

from fpdf import FPDF

ANTHROPIC_MODEL = "claude-opus-5"
GROQ_MODEL = "groq/compound"

# urllib's default "Python-urllib/x.y" User-Agent gets blocked outright by
# Groq's Cloudflare bot protection (403, error code 1010), so send a normal one.
USER_AGENT = "Mozilla/5.0 (compatible; cover-letter-script/1.0)"

PROMPT_TEMPLATE = """You are helping a real job applicant write their own cover letter.

Below is the applicant's resume and the job description they're applying to.

First, figure out the company name and the role title from the job description.
Then research the company (recent news, what they actually build, their mission/values,
anything specific and current you can find) so the letter references real, specific
things about the company instead of generic filler. Use whatever research tools you
have available.

Then write a cover letter in the applicant's voice: specific, direct, no cliches like
"I am excited to apply" or "I believe I would be a great fit". Ground every claim about
the applicant in something actually in their resume. Reference at least one concrete,
current fact about the company that you found. Three to four short paragraphs. No
letterhead, no date, no "Dear ___" greeting, no sign-off -- just the body paragraphs,
since those get added separately.

RESUME:
---
{resume_text}
---

JOB DESCRIPTION:
---
{jd_text}
---

When you're done, end your response with exactly one fenced block like this,
containing nothing but valid JSON with these four keys:

```json
{{"applicant_name": "...", "company_name": "...", "role_title": "...", "letter_body": "..."}}
```

letter_body should contain the full letter body text with paragraphs separated by \\n\\n.
"""


def extract_pdf_text(path):
    result = subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def load_jd_text(path):
    if path.lower().endswith(".pdf"):
        return extract_pdf_text(path)
    with open(path, "r") as f:
        return f.read().strip()


def extract_json_block(text):
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{[^{}]*\"letter_body\"[^{}]*\})", text, re.DOTALL)
    if not match:
        raise ValueError("model response didn't contain the expected JSON block:\n" + text[-2000:])
    return json.loads(match.group(1))


def call_anthropic(prompt, model, max_searches):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY is not set. Get one at console.anthropic.com and export it.")

    body = json.dumps({
        "model": model,
        "max_tokens": 8192,
        "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}],
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Anthropic API error {e.code}: {e.read().decode()}")

    text = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    )
    return text


def call_groq(prompt, model):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("GROQ_API_KEY is not set. Get one at console.groq.com and export it.")

    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Groq API error {e.code}: {e.read().decode()}")

    return data["choices"][0]["message"]["content"]


def sanitize_filename(text):
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "Unknown"


def find_contact_line(resume_text):
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume_text)
    phone = re.search(r"(\+?\d[\d\-\s().]{8,}\d)", resume_text)
    parts = [m.group(0).strip() for m in (email, phone) if m]
    return "  |  ".join(parts)


def build_pdf(fields, resume_text, out_dir):
    pdf = FPDF(format="Letter")
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, fields["applicant_name"], new_x="LMARGIN", new_y="NEXT")

    contact = find_contact_line(resume_text)
    if contact:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, date.today().strftime("%B %d, %Y"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.cell(0, 6, f"Dear {fields['company_name']} Hiring Team,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for paragraph in fields["letter_body"].split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pdf.multi_cell(0, 6, paragraph)
        pdf.ln(4)

    pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, fields["applicant_name"], new_x="LMARGIN", new_y="NEXT")

    name_part = sanitize_filename(fields["applicant_name"])
    company_part = sanitize_filename(fields["company_name"])
    filename = f"{name_part}_{company_part}_Cover_Letter.pdf"
    out_path = os.path.join(out_dir, filename)
    pdf.output(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", required=True, help="path to your resume PDF")
    jd_group = parser.add_mutually_exclusive_group(required=True)
    jd_group.add_argument("--jd", help="path to a job description file (.txt or .pdf)")
    jd_group.add_argument("--jd-text", help="job description text, given directly")
    parser.add_argument("--provider", choices=["anthropic", "groq"], default="anthropic")
    parser.add_argument("--model", help="override the default model id for the chosen provider")
    parser.add_argument("--max-searches", type=int, default=6, help="anthropic only: max web searches")
    parser.add_argument("--out", default=".", help="output directory")
    args = parser.parse_args()

    resume_text = extract_pdf_text(args.resume)
    jd_text = load_jd_text(args.jd) if args.jd else args.jd_text.strip()

    prompt = PROMPT_TEMPLATE.format(resume_text=resume_text, jd_text=jd_text)

    if args.provider == "anthropic":
        raw = call_anthropic(prompt, args.model or ANTHROPIC_MODEL, args.max_searches)
    else:
        raw = call_groq(prompt, args.model or GROQ_MODEL)

    fields = extract_json_block(raw)

    os.makedirs(args.out, exist_ok=True)
    out_path = build_pdf(fields, resume_text, args.out)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
