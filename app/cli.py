import argparse
import asyncio
import sys
from app.session.session import Session
from app.agent.pi_adapter import PiAdapter
from app.events.events import TextChunk, ThinkingChunk, ToolCall, ToolResult, Complete


async def run_cli():
    session = Session()

    print("Agent Voice Shell - CLI Mode")
    print("Type your message and press Enter. Ctrl+C to exit.")
    print()

    while True:
        try:
            user_text = input("You: ").strip()
            if not user_text:
                continue

            session.add_user_turn(user_text)

            print("Agent: ", end="", flush=True)

            async with PiAdapter() as agent:
                async for event in agent.stream(session.get_messages()):
                    if isinstance(event, TextChunk):
                        print(event.delta, end="", flush=True)
                        session.append_assistant_partial(event.delta)
                    elif isinstance(event, ThinkingChunk):
                        pass
                    elif isinstance(event, ToolCall):
                        print(f"\n[Tool call: {event.name}]", end="", flush=True)
                    elif isinstance(event, ToolResult):
                        print(f"\n[Tool result: {event.result}]", end="", flush=True)
                    elif isinstance(event, Complete):
                        session.finalize_assistant()
                        print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")
            break


def main():
    parser = argparse.ArgumentParser(description="Agent Voice Shell CLI")
    args = parser.parse_args()

    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
