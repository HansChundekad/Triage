"""Run the ReproAgent echo process: python -m triage.repro_agent"""
import asyncio

from triage.repro_agent.echo import run

if __name__ == "__main__":
    asyncio.run(run())
