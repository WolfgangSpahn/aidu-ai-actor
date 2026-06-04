# !/bin/bash

curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "role": "teacher",
    "content": "What is 4+3?"
  }'