import json
import time

from pydantic import BaseModel


def request_json(
    *, client, model: str, system_prompt: str, payload: dict,
    response_model: type[BaseModel], delay_between_requests: float = 0.0,
) -> dict:
    request_kwargs = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        },
    }
    if delay_between_requests > 0:
        time.sleep(delay_between_requests)
    response = client.chat.completions.create(**request_kwargs)
    choice = response.choices[0]
    if choice.finish_reason != "stop":
        raise ValueError(f"Unexpected finish_reason: {choice.finish_reason!r}; expected 'stop'")
    if choice.message.refusal:
        raise ValueError(f"Model refused the request: {choice.message.refusal}")
    if not choice.message.content:
        raise ValueError("Model returned no text content")
    return json.loads(choice.message.content)

