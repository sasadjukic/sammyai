import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from rag.rag_system import RAGSystem

def test_indexing():
    print("Initializing RAG system...")
    rag = RAGSystem()
    
    test_file = "text_editor.py"
    print(f"Indexing {test_file}...")
    try:
        success = rag.index_file(test_file)
        print(f"Indexing result: {success}")
        
        if success:
            print("Getting context...")
            context = rag.get_context("How is the toolbar created?", top_k=2)
            print("Context retrieved successfully.")
            print(f"Retrieved {len(context.chunks)} chunks.")
            print("Formatting for LLM...")
            print(context.format_for_llm())
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_indexing()
