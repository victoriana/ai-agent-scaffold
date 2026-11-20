# Pseudo-code for your mental model
# 1. Load docs (PDF/Markdown)
# 2. Chunk using RecursiveCharacterTextSplitter
# 3. Embed using Vertex AI / OpenAI embeddings
# 4. Store in Vector DB (Pinecone/FAISS/Chroma)
# 5. Retrieve top-k chunks based on query similarity
