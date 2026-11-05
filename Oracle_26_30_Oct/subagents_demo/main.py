"""
=====================================================================
FILE: main.py
=====================================================================
PURPOSE
    Runs the supervisor + 3 subagents on the 2 PDFs and prints:
      1. every step in order (who ran, what it received, time taken)
      2. each subagent's output
      3. the final decision note

WHAT PROBLEM IT SOLVES
    Lets students watch the flow:
    supervisor -> extractor -> supervisor -> analyst -> supervisor
    -> writer -> supervisor -> FINISH

HOW TO RUN
    From the project root (after generating the PDFs):
        python main.py

EXPECTED OUTPUT
    A numbered step log (7 steps), then the 3 subagent outputs.
    The last output starts with "Decision: Shortlist" or "Decision: Reject".
=====================================================================
"""

# The function that builds our supervisor graph.
from app.supervisor import build_graph


# The overall goal the supervisor works towards.
GOAL = "Screen the candidate in candidate_resume.pdf for the role in job_description.pdf and recommend shortlist or reject."


def main() -> None:
    """Run the graph once and print the results."""
    # Build the compiled graph.
    graph = build_graph()
    # Run it. results starts empty; trace collects every step.
    final = graph.invoke({"goal": GOAL, "results": {}, "next": "", "instruction": "", "trace": []})

    # ---- 1. Step-by-step flow ----
    print("\n=== FLOW ===")
    # Print each logged step with a step number.
    for i, step in enumerate(final["trace"], start=1):
        # Supervisor steps show the decision and the task it wrote.
        if step["step"] == "supervisor":
            print(f"{i}. SUPERVISOR -> {step['decided']:<9} ({step['ms']} ms) "
                  f"[LLM choice accepted: {step['llm_choice_accepted']}]")
            # Show the task only when a subagent is chosen.
            if step["decided"] != "FINISH":
                print(f"     task: {step['instruction']}")
        # Subagent steps show what input they received.
        else:
            print(f"{i}.   {step['step'].upper():<10} received: {step['received']:<12} "
                  f"output: {step['output_chars']} chars ({step['ms']} ms)")

    # ---- 2. Each subagent's output ----
    for name, output in final["results"].items():
        # Heading for this subagent.
        print(f"\n=== {name.upper()} OUTPUT ===")
        # Its full output.
        print(output)


# Run only when executed directly.
if __name__ == "__main__":
    main()
