# !/bin/bash

curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "content": "Please don't guess, what is a first step?"
  }'