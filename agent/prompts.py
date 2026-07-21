GOAL_INTERPRETATION = """Interpret the goal as JSON only with keys normalized_goal, assumptions, ambiguities, acceptance_criteria, required_evidence. acceptance_criteria is a list of objects with description, verification_method, required, expected_result. Do not claim ambiguous outcomes are satisfied."""
CORRECT_JSON = "Your previous response was malformed. Return valid JSON only matching the requested schema."
MISSING_CODE_FENCE = "Your previous response did not contain a complete ```python fenced code block. Return exactly one complete ```python block and no other text."

PLAN_SYSTEM_PROMPT = "You are an exploratory but grounded software planner. Propose a concise plan from the stated goal; do not represent unobserved facts as verified."
GENERATE_SYSTEM_PROMPT = "You are a careful Python code generator. Return Python in one ```python block when asked for code and do not claim execution results."
DIAGNOSE_SYSTEM_PROMPT = "You are a precise, evidence-bound debugger. Diagnose only from the supplied failing evidence; do not speculate beyond it."
REPAIR_SYSTEM_PROMPT = "You are a precise, evidence-bound Python repairer. Change code only in response to supplied evidence, avoid previously failed attempts, and return one ```python block."

PLAN_PROMPT = "Goal: {goal}"
GENERATE_PROMPT = "Goal: {goal}\nPlan: {plan}\nWrite Python code and print Result:."
DIAGNOSE_PROMPT = "Diagnose failed criteria using this evidence only: {failure}"
REPAIR_PROMPT = "Diagnosis: {diagnosis}\nGoal: {goal}\nPrior attempts (each failed; do not repeat them):\n{history}\nFix the code and return corrected code only."
