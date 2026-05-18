"""
Main Entry Point for RAG2 Self-RAG System

This script provides an interactive CLI interface for the Self-RAG system.
It initializes all components, runs health checks, and processes user questions
through the multi-hop retrieval workflow.
"""

import sys
from colorama import init, Fore, Style, Back
from src.config.settings import config, get_mode_display
from src.utils.checks import check_local_mode_prerequisites
from src.ingestion.loader import get_vector_store
from src.graph.workflow import create_self_rag_workflow, initialize_state
from src.graph.nodes import vector_store


# Initialize colorama for colored terminal output
init(autoreset=True)


def print_header():
    """Print the system header with current mode."""
    print("\n" + "=" * 70)
    print(f"{Fore.CYAN}{' ' * 15}RAG2 - Self-RAG System{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{' ' * 20}{get_mode_display()}{Style.RESET_ALL}")
    print("=" * 70 + "\n")


def print_separator(char="─"):
    """Print a visual separator."""
    print(Fore.LIGHTBLACK_EX + char * 70 + Style.RESET_ALL)


def print_section(title: str, color=Fore.BLUE):
    """Print a section header."""
    print(f"\n{color}{title}{Style.RESET_ALL}")
    print_separator()


def print_iteration_info(iteration: int, max_iterations: int):
    """
    Print iteration information.
    
    Args:
        iteration: Current iteration number (already incremented in retrieve_node)
        max_iterations: Maximum allowed iterations
    """
    print(f"\n{Fore.MAGENTA}🔄 Iteration {iteration}/{max_iterations}{Style.RESET_ALL}")
    print_separator("─")


def print_retrieval_info(context: list):
    """Print retrieval information and context summary."""
    print(f"{Fore.CYAN}🔍 Retrieval{Style.RESET_ALL}")
    print(f"   Retrieved {len(context)} documents\n")
    
    for i, doc in enumerate(context[:2], 1):  # Show first 2 docs
        # Access Document object properties
        content = doc.page_content
        source = doc.metadata.get("source", "Unknown")
        
        preview = content[:150] + "..." if len(content) > 150 else content
        print(f"   {Fore.GREEN}[Document {i}] {source}{Style.RESET_ALL}")
        print(f"      {preview}")
    
    if len(context) > 2:
        print(f"   {Fore.LIGHTBLACK_EX}... and {len(context) - 2} more documents{Style.RESET_ALL}")


def print_generation_info(answer: str, grade: str, reason: str):
    """Print generation and grading information."""
    print(f"\n{Fore.CYAN}💭 Generation & Grading{Style.RESET_ALL}")
    
    # Display grade with appropriate color
    if grade == "YES":
        grade_display = f"{Fore.GREEN}✅ YES{Style.RESET_ALL}"
    else:
        grade_display = f"{Fore.RED}❌ NO{Style.RESET_ALL}"
    
    print(f"   Grade: {grade_display}")
    print(f"   Reason: {Fore.YELLOW}{reason}{Style.RESET_ALL}")
    
    # Display answer preview
    answer_preview = answer[:200] + "..." if len(answer) > 200 else answer
    print(f"\n   {Fore.BLUE}Answer Preview:{Style.RESET_ALL}")
    print(f"   {answer_preview}")


def print_query_rewriting(old_query: str, new_query: str):
    """Print query rewriting information."""
    print(f"\n{Fore.MAGENTA}✏️ Query Rewriting{Style.RESET_ALL}")
    print(f"   {Fore.YELLOW}Old Query:{Style.RESET_ALL} {old_query}")
    print(f"   {Fore.GREEN}New Query:{Style.RESET_ALL} {new_query}")


def print_final_answer(answer: str, grade: str, iterations: int, reason: str = ""):
    """Print the final answer with metadata."""
    print_separator()
    print(f"\n{Fore.GREEN}✨ Final Answer{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
    
    print(answer)
    
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"\n{Fore.LIGHTBLACK_EX}Metadata:{Style.RESET_ALL}")
    print(f"   Iterations: {iterations}")
    print(f"   Final Grade: {Fore.GREEN if grade == 'YES' else Fore.RED}{grade}{Style.RESET_ALL}")
    if reason:
        print(f"   Reason: {reason}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Back.RED}{Fore.WHITE}ERROR: {message}{Style.RESET_ALL}\n")


def run_health_checks():
    """Run system health checks based on current mode."""
    print_section("🔍 System Health Checks")
    
    if config.MODE == "LOCAL":
        try:
            check_local_mode_prerequisites()
        except Exception as e:
            print_error(str(e))
            print(f"{Fore.YELLOW}Please fix the issues above and try again.{Style.RESET_ALL}")
            sys.exit(1)
    else:
        # Cloud mode - verify API key
        if not config.OPENAI_API_KEY:
            print_error("OPENAI_API_KEY is not set in .env file")
            print(f"{Fore.YELLOW}Please set your OpenAI API key in the .env file.{Style.RESET_ALL}")
            sys.exit(1)
        print(f"{Fore.GREEN}✅ Cloud mode: API key is configured{Style.RESET_ALL}")


def initialize_system():
    """Initialize all system components."""
    print_section("⚙️ System Initialization")
    
    # Initialize vector store
    print(f"{Fore.CYAN}Loading vector store...{Style.RESET_ALL}")
    global vector_store
    vector_store = get_vector_store()
    
    # Set vector store in nodes module
    from src.graph import nodes
    nodes.vector_store = vector_store
    
    # Create workflow
    print(f"{Fore.CYAN}Compiling Self-RAG workflow...{Style.RESET_ALL}")
    workflow = create_self_rag_workflow(max_iterations=config.MAX_ITERATIONS)
    
    print(f"{Fore.GREEN}✅ System initialized successfully{Style.RESET_ALL}")
    print(f"   Max Iterations: {config.MAX_ITERATIONS}")
    print(f"   Retrieval K: {config.RETRIEVAL_K}")
    
    return workflow


def process_question(question: str, workflow) -> dict:
    """
    Process a user question through the Self-RAG workflow.
    
    Args:
        question: User's question
        workflow: Compiled LangGraph workflow
        
    Returns:
        Final state after processing
    """
    print_section(f"📝 Question: {question}")
    
    # Initialize state
    state = initialize_state(question, max_iterations=config.MAX_ITERATIONS)
    
    # Track iterations for verbose output
    previous_query = question
    
    # Execute workflow with callback for verbose output
    result = None
    for step in workflow.stream(state):
        for node_name, node_state in step.items():
            if node_name == "retrieve":
                print_iteration_info(node_state["iterations"], config.MAX_ITERATIONS)
                print_retrieval_info(node_state["context"])
                
            elif node_name == "generate_and_grade":
                print_generation_info(
                    node_state["answer"],
                    node_state["grade"],
                    node_state["reason"]
                )
                
                # Track query for potential rewriting
                previous_query = node_state["current_query"]
                
            elif node_name == "rewrite_query":
                print_query_rewriting(previous_query, node_state["current_query"])
                previous_query = node_state["current_query"]
            
            result = node_state
    
    # Print final answer
    print_final_answer(
        result["answer"],
        result["grade"],
        result["iterations"],
        result["reason"] if result["grade"] == "NO" else "Answer quality is good"
    )
    
    return result


def main():
    """Main entry point for the RAG2 system."""
    try:
        # Print header
        print_header()
        
        # Run health checks
        run_health_checks()
        
        # Initialize system
        workflow = initialize_system()
        
        # Start interactive loop
        print_section("🚀 Ready to Answer Questions")
        print(f"{Fore.LIGHTBLACK_EX}Type your question below, or 'quit' to exit.{Style.RESET_ALL}\n")
        
        while True:
            # Get user input
            try:
                question = input(f"{Fore.CYAN}Question{Style.RESET_ALL} > ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n{Fore.YELLOW}Exiting...{Style.RESET_ALL}")
                break
            
            # Check for exit command
            if not question or question.lower() in ["quit", "exit", "q"]:
                print(f"\n{Fore.YELLOW}Thank you for using RAG2 Self-RAG System!{Style.RESET_ALL}\n")
                break
            
            # Process question
            try:
                process_question(question, workflow)
            except Exception as e:
                print_error(f"Failed to process question: {str(e)}")
                import traceback
                traceback.print_exc()
            
            print("\n")  # Add spacing between questions
    
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Interrupted. Exiting...{Style.RESET_ALL}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()