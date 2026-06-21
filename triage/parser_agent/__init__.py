"""ParserAgent — posts structured repro steps into the Band room @ReproAgent.

Phase 3: echo only. Connects as the BAND_PARSER_* identity, posts ONE
hardcoded placeholder-steps message @mentioning ReproAgent, and acks any
message that @mentions it. Real GitHub-fetch + Claude parsing is Phase 5.

Run: ``python -m triage.parser_agent`` (with a filled-in .env).
"""
