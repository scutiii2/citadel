from src.gateway.conversation.contract import Limits, parse_request

LIMITS = Limits(max_messages=500, max_text=400_000, max_tools=128, max_images=20, max_image_bytes=16 * 1024 * 1024)


def chat(gateway: str = "g", **fields):
    """A parsed ChatRequest; keyword arguments are request fields."""
    return parse_request({"gateway": gateway, "messages": [{"role": "user", "content": "Hi"}], **fields}, LIMITS)
