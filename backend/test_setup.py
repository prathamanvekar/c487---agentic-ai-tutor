try:
    from langchain.chains import create_retrieval_chain
    print("SUCCESS: 'create_retrieval_chain' found!")
except ImportError as e:
    print(f"FAIL: Still broken. Error: {e}")

try:
    from langchain_groq import ChatGroq
    print("SUCCESS: 'ChatGroq' found!")
except ImportError as e:
    print(f"FAIL: ChatGroq broken. Error: {e}")
