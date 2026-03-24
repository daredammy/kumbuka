"""Shared rendering helpers for meeting notes."""


def format_notes(result: dict) -> str:
    """Format structured output as readable markdown."""
    sections = []

    title = result.get("title", "Untitled Meeting")
    sections.append(f"# {title}")

    participants = result.get("participants", [])
    if participants:
        sections.append("## Participants")
        sections.append("\n".join(f"- {p}" for p in participants))

    summary = result.get("summary", "")
    if summary:
        sections.append("## Summary")
        sections.append(summary)

    feedback = result.get("feedback", "")
    if feedback:
        sections.append("## Communication Feedback")
        sections.append(feedback)

    transcript = result.get("transcript", "")
    if transcript:
        sections.append("## Transcript")
        sections.append(transcript)

    return "\n\n".join(sections)
