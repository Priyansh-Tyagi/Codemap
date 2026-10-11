"""
Checks your Gemini API key exactly the way CodeMap uses it - same .env file,
same model, same header - and says what the result means.

    cd backend\\app
    python check_gemini.py

Works the same in Command Prompt and PowerShell; nothing to paste.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=False)

from analyzer import ai_tour  # noqa: E402


def _reason(resp) -> str:
    return ai_tour._provider_message(resp) or "(no message from Google)"


def main() -> int:
    key = ai_tour._api_key()
    if not key:
        print("GEMINI_API_KEY is not set. Put it in backend\\app\\.env as:  GEMINI_API_KEY=your-key")
        return 1

    url = ai_tour._api_url()
    headers = {"x-goog-api-key": key}
    print(f"Key:   {len(key)} characters, starts with {key[:4]!r} (AI Studio keys start with 'AIza' or 'AQ.')")
    model = url.rsplit("/models/", 1)[1].split(":")[0]
    source = "GEMINI_MODEL in your .env" if os.environ.get("GEMINI_MODEL") else "built-in default (set GEMINI_MODEL in .env to change)"
    print(f"Model: {model}  <- from {source}\n")

    try:
        listed = requests.get(f"{ai_tour.GEMINI_BASE_URL}?pageSize=1", headers=headers, timeout=20)
        print(f"1) Does the key authenticate at all (list models)?  ->  HTTP {listed.status_code}")
        if not listed.ok:
            print(f"   Google says: {_reason(listed)}")

        gen = requests.post(
            url, headers=headers, timeout=30,
            json={"contents": [{"parts": [{"text": "Reply with the single word: ready"}]}]},
        )
        print(f"2) Can it generate text with this model?            ->  HTTP {gen.status_code}")
        if gen.ok:
            parts = (gen.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            print(f"   Model replied: {text or '(empty reply)'}")
        else:
            print(f"   Google says: {_reason(gen)}")
    except requests.RequestException as e:
        print(f"Could not reach Google at all ({type(e).__name__}). Check your internet connection or proxy.")
        return 2

    print()
    if listed.ok and gen.ok:
        print("RESULT: the key and model work. If narration still fails in CodeMap, send me the error shown there.")
        return 0
    if listed.ok and gen.status_code == 402:
        print("RESULT: the key is fine - this is a BILLING problem on the Google project the key belongs to\n"
              "        (prepaid credits used up). Add credits at https://ai.studio/projects, or use a key from a\n"
              "        project that is on the free tier. Changing GEMINI_MODEL may not help, since billing is\n"
              "        per project - but it is a cheap thing to try, because some newer models are paid-only.")
        return 5
    if listed.ok and not gen.ok:
        print("RESULT: the key is accepted, but this model/request is refused. Try another model: set GEMINI_MODEL\n"
              "        in .env (e.g. gemini-2.5-flash), or check the message above for a quota/billing reason.")
        return 3
    print("RESULT: Google rejects the key itself, so no code change in CodeMap can fix it. Create a new key at\n"
          "        https://aistudio.google.com/apikey (use its copy button - a truncated paste is common), ideally\n"
          "        in a different project, and put it in .env. Other developers report this same 401 with new\n"
          "        'AQ.' keys on some accounts; if a fresh key fails too, it's on Google's side.")
    return 4


if __name__ == "__main__":
    sys.exit(main())
