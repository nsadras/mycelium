"""Independent chat summaries and message records in the canonical database."""

from __future__ import annotations


class SessionStore:
    def __init__(self, db):
        self.db = db

    def summaries(self):
        return {
            identifier: self.db.get("sessions", identifier)
            for identifier in self.db.ids("sessions")
        }

    def get(self, identifier):
        summary = self.db.get("sessions", identifier)
        messages = [
            self.db.get("messages", key)["message"]
            for key in self.db.ids("messages", "session_id", identifier)
        ]
        return {**summary, "transcript": messages}

    def save(self, identifier, record):
        messages = record.get("transcript", [])
        summary = {key: value for key, value in record.items() if key != "transcript"}
        summary["message_count"] = len(messages)
        summary.setdefault("captured_turns", 0)
        with self.db.transaction():
            self.db.put("sessions", identifier, summary)
            for index, message in enumerate(messages):
                self.db.put(
                    "messages",
                    f"{identifier}:{index:012d}",
                    {"session_id": identifier, "message": message},
                )
            for key in self.db.ids("messages", "session_id", identifier)[
                len(messages) :
            ]:
                self.db.delete("messages", key)

    def rename(self, identifier, name):
        summary = self.db.get("sessions", identifier)
        summary["query"] = name
        self.db.put("sessions", identifier, summary)
