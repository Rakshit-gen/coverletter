#!/usr/bin/env python3
"""Very small local web UI on top of cover_letter.py. No extra dependencies."""
import email
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cover_letter as cl

INDEX_HTML = """<!doctype html>
<html><head><title>Cover Letter Generator</title>
<style>
body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px}
label{display:block;margin-top:16px;font-weight:600}
input,select,textarea{width:100%;padding:8px;margin-top:4px;box-sizing:border-box;font:inherit}
textarea{height:160px}
button{margin-top:20px;padding:10px 20px;font-size:15px;cursor:pointer}
#status{margin-top:16px;color:#555}
</style></head>
<body>
<h2>Cover Letter Generator</h2>
<form id="f">
  <label>Resume (PDF)</label>
  <input type="file" name="resume" accept="application/pdf" required>

  <label>Job description</label>
  <textarea name="jd_text" placeholder="Paste the job description here" required></textarea>

  <label>Provider</label>
  <select name="provider">
    <option value="anthropic">Anthropic (Claude, native web search)</option>
    <option value="groq">Groq (compound, fast)</option>
  </select>

  <button type="submit">Generate cover letter</button>
</form>
<div id="status"></div>
<script>
const f = document.getElementById('f');
const status = document.getElementById('status');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  status.textContent = 'Researching the company and writing the letter, this can take a minute...';
  const resp = await fetch('/generate', {method: 'POST', body: new FormData(f)});
  if (!resp.ok) {
    status.textContent = 'Error: ' + await resp.text();
    return;
  }
  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : 'cover_letter.pdf';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  status.textContent = 'Done: ' + filename;
});
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        body = INDEX_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/generate":
            self.send_response(404)
            self.end_headers()
            return
        try:
            resume_bytes, jd_text, provider = self._parse_form()
            if not resume_bytes or not jd_text:
                raise ValueError("missing resume file or job description")

            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                tmp.write(resume_bytes)
                tmp.flush()
                resume_text = cl.extract_pdf_text(tmp.name)

            cl.check_input_sizes(resume_text, jd_text)
            prompt = cl.PROMPT_TEMPLATE.format(resume_text=resume_text, jd_text=jd_text)
            if provider == "groq":
                raw = cl.call_groq(prompt, cl.GROQ_MODEL)
            else:
                raw = cl.call_anthropic(prompt, cl.ANTHROPIC_MODEL, 6)

            fields = cl.extract_json_block(raw)

            with tempfile.TemporaryDirectory() as tmp_dir:
                out_path = cl.build_pdf(fields, resume_text, tmp_dir)
                with open(out_path, "rb") as f:
                    pdf_bytes = f.read()
                filename = os.path.basename(out_path)

            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)
        except SystemExit as e:
            self._send_error(str(e))
        except Exception as e:
            self._send_error(str(e))

    def _parse_form(self):
        length = int(self.headers["Content-Length"])
        raw_body = self.rfile.read(length)
        header_bytes = b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n"
        msg = email.message_from_bytes(header_bytes + raw_body)

        resume_bytes, jd_text, provider = None, None, "anthropic"
        for part in msg.get_payload():
            name = part.get_param("name", header="Content-Disposition")
            if name == "resume":
                resume_bytes = part.get_payload(decode=True)
            elif name == "jd_text":
                jd_text = part.get_payload(decode=True).decode()
            elif name == "provider":
                provider = part.get_payload(decode=True).decode()
        return resume_bytes, jd_text, provider

    def _send_error(self, message):
        body = message.encode()
        self.send_response(500)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"open http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
