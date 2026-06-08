#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional: create an OpenAI Vector Store from the original txt.

Prerequisites:
  pip install openai
  export OPENAI_API_KEY="..."

Run:
  python openai_vector_store_setup.py

This script is provided as a template. It was not executed in this environment.
"""
from openai import OpenAI

client = OpenAI()

vector_store = client.vector_stores.create(name="教材 RAG Vector Store")

with open("source/教材(1).txt", "rb") as f:
    file_batch = client.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id,
        files=[f],
    )

print("vector_store_id:", vector_store.id)
print("file_batch_status:", file_batch.status)
print("file_counts:", file_batch.file_counts)
