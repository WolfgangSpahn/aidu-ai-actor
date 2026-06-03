from __future__ import annotations

import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from aidu.ai.actor.message import ActorMessage
from aidu.ai.actor.service import ActorService


def create_actor_app(service: ActorService) -> FastAPI:
    app = FastAPI()

    @app.post("/messages")
    def post_message(msg: ActorMessage):
        return service.receive(msg)

    @app.get("/events")
    def events():
        def stream():
            while True:
                if service.outbox:
                    msg = service.outbox.popleft()
                    yield f"data: {msg.model_dump_json()}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/health")
    def health():
        return {"actor": service.actor_id, "status": "ok"}

    return app

def main():
    from aidu.ai.actor.demo.actor import DemoActor
    from aidu.ai.actor.service import ActorService

    actor = DemoActor()
    service = ActorService(actor_id="demo-actor")
    app = create_actor_app(service)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    

if __name__ == "__main__":
    main()