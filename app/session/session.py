class Session:
    def __init__(self):
        self.messages: list[dict] = []
        self.assistant_partial: str = ""

    def add_user_turn(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant_partial(self, chunk: str) -> None:
        self.assistant_partial += chunk

    def finalize_assistant(self) -> None:
        if self.assistant_partial:
            self.messages.append({"role": "assistant", "content": self.assistant_partial})
            self.assistant_partial = ""

    def discard_assistant_partial(self) -> None:
        self.assistant_partial = ""

    def get_messages(self) -> list[dict]:
        if self.assistant_partial:
            return self.messages + [{"role": "assistant", "content": self.assistant_partial}]
        return self.messages
