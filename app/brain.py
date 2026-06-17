"""
The conversational brain of the AI receptionist.

Phase 1: pure text conversation. It talks like a human receptionist, keeps
track of the multi-turn conversation, and gathers the details needed to book,
cancel, or answer questions. It does NOT touch a real calendar yet -- that is
Phase 2. For now it collects the relevant details and tells the caller a human
will confirm, so we can verify the conversation quality first.
"""

from __future__ import annotations

import ollama

from . import config


def _system_prompt() -> str:
    b = config.BUSINESS
    services = ", ".join(b["services"])
    return f"""You are {b['receptionist_name']}, the friendly receptionist for \
{b['name']}, a {b['kind']}.

You are in the middle of a phone call with a caller. You have ALREADY greeted \
them. Your replies will be read out loud, so follow these rules strictly:
- NEVER greet, welcome, or say "Hello" again. The call is already in progress.
- Keep replies SHORT and natural, like real speech. One or two sentences max.
- Sound warm and human. Never say you are an AI or a language model.
- Ask only ONE question at a time, and only ask for information you do not \
already have.
- Carefully remember details the caller has given (name, service, day, time) \
and never ask for the same thing twice.

Business facts (only state these if asked or relevant):
- Hours: {b['hours']}
- Services: {services}
- Address: {b['address']}
- Phone: {b['phone']}

Your job is to help the caller with one of three things:
1. BOOK an appointment.
2. CANCEL an existing appointment.
3. Answer a QUESTION about the business.

When booking, naturally collect: the caller's name, which service they want, \
and their preferred day and time. Do not invent available slots or confirm a \
real booking yet -- once you have the details, say you'll get it confirmed and \
someone will be in touch. When cancelling, collect their name and which \
appointment to cancel.

Start by greeting the caller and asking how you can help."""


class Receptionist:
    """Holds one conversation's state and produces replies."""

    def __init__(self) -> None:
        self.messages: list[dict] = [
            {"role": "system", "content": _system_prompt()}
        ]
        self._client = ollama.Client(host=config.OLLAMA_HOST)

    def greeting(self) -> str:
        """Return the opening line.

        Kept as a fixed, natural line rather than model-generated: a real
        receptionist opens consistently, it's instant, and it avoids the model
        rambling when there's no caller message to respond to yet.
        """
        b = config.BUSINESS
        line = (
            f"Thank you for calling {b['name']}, this is "
            f"{b['receptionist_name']}. How can I help you today?"
        )
        print(line)
        self.messages.append({"role": "assistant", "content": line})
        return line

    def reply(self, user_text: str) -> str:
        """Add the caller's message and stream back the receptionist's reply."""
        self.messages.append({"role": "user", "content": user_text})
        return self._generate()

    def _generate(self) -> str:
        """Stream a reply token-by-token, print it, and store it."""
        full = []
        stream = self._client.chat(
            model=config.CHAT_MODEL,
            messages=self.messages,
            stream=True,
            options={"temperature": 0.6},
        )
        for chunk in stream:
            piece = chunk["message"]["content"]
            full.append(piece)
            print(piece, end="", flush=True)
        print()
        text = "".join(full).strip()
        self.messages.append({"role": "assistant", "content": text})
        return text


def detect_intent(user_text: str) -> str:
    """Quick, cheap classification of what the caller wants.

    Returns one of: booking, cancellation, question, other.
    Used only for the --show-intent debug view; not part of the reply path.
    """
    client = ollama.Client(host=config.OLLAMA_HOST)
    prompt = (
        "Classify the caller's message into exactly one word: "
        "booking, cancellation, question, or other.\n"
        f'Message: "{user_text}"\n'
        "Answer with only the single word."
    )
    resp = client.generate(
        model=config.INTENT_MODEL,
        prompt=prompt,
        options={"temperature": 0.0},
    )
    raw = resp["response"].strip().lower()
    for label in ("booking", "cancellation", "question", "other"):
        if label in raw:
            return label
    return "other"
