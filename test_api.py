"""
Test Program for RAG2 API Module

This script demonstrates how to use the RAG2 API module and provides
comprehensive tests for all its features.

Usage:
    python test_api.py
"""

import sys
import json
from src.api.rag_api import RAG2API, ask_question


def print_separator(title: str = "", length: int = 70):
    """Print a visual separator."""
    if title:
        print(f"\n{'=' * length}")
        print(f"  {title}")
        print(f"{'=' * length}\n")
    else:
        print(f"{'=' * length}\n")


def print_result(result: dict, show_details: bool = False):
    """Print result in a formatted way."""
    print(f"✅ Success: {result.get('success', False)}")
    print(f"📝 Question: {result.get('question', 'N/A')}")
    print(f"💭 Answer: {result.get('answer', 'N/A')}")
    print(f"📊 Grade: {result.get('grade', 'N/A')}")
    print(f"🔄 Iterations: {result.get('iterations', 0)}")
    print(f"💡 Reason: {result.get('reason', 'N/A')}")
    
    if show_details and 'context' in result:
        print(f"\n📚 Retrieved Context ({len(result['context'])} documents):")
        for i, ctx in enumerate(result['context'], 1):
            print(f"   [{i}] Source: {ctx.get('source', 'Unknown')}")
            print(f"       Content: {ctx.get('content', '')[:100]}...")
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")


def test_1_basic_usage():
    """Test 1: Basic usage with RAG2API class."""
    print_separator("Test 1: Basic Usage with RAG2API Class")
    
    try:
        # Initialize API
        print("Initializing RAG2 API...")
        api = RAG2API()
        
        # Ask a question
        question = "什么是 Self-RAG？"
        print(f"\nAsking: {question}")
        result = api.ask(question)
        
        # Print result
        print_result(result, show_details=False)
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_2_quick_function():
    """Test 2: Quick function usage."""
    print_separator("Test 2: Quick Function Usage")
    
    try:
        question = "LangGraph 的主要特点是什么？"
        print(f"Asking: {question}")
        
        # Use quick function
        result = ask_question(question)
        
        # Print result
        print_result(result)
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_3_with_context():
    """Test 3: Ask with context returned."""
    print_separator("Test 3: Ask with Retrieved Context")
    
    try:
        api = RAG2API()
        
        question = "Self-RAG 和标准 RAG 的区别是什么？"
        print(f"Asking: {question}")
        print("Returning retrieved documents...\n")
        
        # Ask with context
        result = api.ask(question, return_context=True)
        
        # Print result with context
        print_result(result, show_details=True)
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_4_batch_ask():
    """Test 4: Batch processing of multiple questions."""
    print_separator("Test 4: Batch Processing")
    
    try:
        api = RAG2API()
        
        questions = [
            "什么是 Self-RAG？",
            "LangGraph 的主要特点是什么？",
            "Self-RAG 如何进行多跳推理？"
        ]
        
        print(f"Processing {len(questions)} questions in batch...\n")
        
        # Batch ask
        results = api.batch_ask(questions)
        
        # Print results
        for i, (q, r) in enumerate(zip(questions, results), 1):
            print(f"\n{'─' * 70}")
            print(f"Question {i}: {q}")
            print(f"{'─' * 70}")
            print(f"Answer: {r['answer'][:150]}...")
            print(f"Grade: {r['grade']}, Iterations: {r['iterations']}")
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_5_health_check():
    """Test 5: Health check and statistics."""
    print_separator("Test 5: Health Check and Statistics")
    
    try:
        api = RAG2API()
        
        # Health check
        print("Performing health check...\n")
        health = api.health_check()
        print(f"Status: {health['status']}")
        print(f"Mode: {health['mode']}")
        print(f"Initialized: {health['initialized']}")
        print(f"Workflow Ready: {health['workflow_ready']}")
        print(f"Vector Store Ready: {health['vector_store_ready']}")
        
        # Statistics
        print("\nFetching statistics...\n")
        stats = api.get_statistics()
        print(f"Documents: {stats['documents']}")
        print(f"Chunks: {stats['chunks']}")
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_6_error_handling():
    """Test 6: Error handling."""
    print_separator("Test 6: Error Handling")
    
    try:
        api = RAG2API()
        
        # Test with empty question
        print("Testing with empty question...")
        result = api.ask("")
        print(f"Empty question handled: {not result['success']}")
        
        # Test with very long question
        print("\nTesting with very long question...")
        long_question = "测试 " * 1000
        result = api.ask(long_question)
        print(f"Long question handled: {result['success']}")
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_7_singleton_pattern():
    """Test 7: Singleton pattern verification."""
    print_separator("Test 7: Singleton Pattern")
    
    try:
        # Create multiple instances
        print("Creating multiple API instances...\n")
        api1 = RAG2API()
        api2 = RAG2API()
        
        # Check if they are the same instance
        print(f"api1 is api2: {api1 is api2}")
        print(f"api1 id: {id(api1)}")
        print(f"api2 id: {id(api2)}")
        
        if api1 is api2:
            print("\n✅ Singleton pattern working correctly!")
        else:
            print("\n❌ Singleton pattern not working!")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("  RAG2 API Module Test Suite")
    print("=" * 70)
    
    tests = [
        ("Basic Usage", test_1_basic_usage),
        ("Quick Function", test_2_quick_function),
        ("With Context", test_3_with_context),
        ("Batch Processing", test_4_batch_ask),
        ("Health Check", test_5_health_check),
        ("Error Handling", test_6_error_handling),
        ("Singleton Pattern", test_7_singleton_pattern),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {str(e)}")
            results.append((name, False))
    
    # Summary
    print_separator("Test Summary")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\n{'=' * 70}")
    print(f"  Total: {passed}/{total} tests passed")
    print(f"{'=' * 70}\n")
    
    return all(success for _, success in results)


def interactive_mode():
    """Interactive mode for manual testing."""
    print("\n" + "=" * 70)
    print("  RAG2 API - Interactive Mode")
    print("=" * 70)
    print("\nType your questions below, or 'quit' to exit.\n")
    
    api = RAG2API()
    
    while True:
        try:
            question = input("Question > ").strip()
            
            if not question or question.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            print("\n🔄 Processing...")
            result = api.ask(question)
            
            print("\n💬 Answer:")
            print(result['answer'])
            
            print(f"\n📊 Grade: {result['grade']} | Iterations: {result['iterations']}")
            print(f"💡 Reason: {result['reason']}")
            
            print("\n" + "=" * 70 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Exiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}\n")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test RAG2 API Module")
    parser.add_argument(
        "--mode",
        choices=["test", "interactive"],
        default="test",
        help="Run mode: 'test' for automated tests, 'interactive' for manual testing"
    )
    
    args = parser.parse_args()
    
    if args.mode == "test":
        success = run_all_tests()
        sys.exit(0 if success else 1)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()