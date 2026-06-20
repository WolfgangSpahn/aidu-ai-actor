# !/bin/bash

curl \
  -X POST "http://localhost:8000/run" -H "Content-Type: application/json" \
  -d '{"summary": "Test run", "messages": [{"role": "user", "content": "Hello"}], "actor": "math_student", "role": "user", "content": "Hello"}'
