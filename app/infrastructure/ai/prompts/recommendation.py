"""
Prompt construction module for AI transfer recommendation ranking.
Exposes only prevalidated candidate data and business identifiers.
Explicitly restricts AI authority from altering quantity, cost, or inventing candidates.
"""

from app.services.dtos import AIRecommendationInputDTO


def build_recommendation_prompt(input_data: AIRecommendationInputDTO) -> str:
    """
    Constructs a structured prompt for Gemini model to select the optimal source DC.

    Strict AI Guardrails enforced in prompt:
    - Select exactly one candidate_id from the pre-validated candidates list.
    - Do NOT invent or modify candidate data.
    - Do NOT calculate or propose transfer quantity.
    - Do NOT calculate or modify cost.
    - Return only the selected candidate_id and a concise rationale.
    """
    candidates_formatted: list[str] = []
    for c in input_data.prevalidated_candidates:
        candidates_formatted.append(
            f"- candidate_id: {c.candidate_id}\n"
            f"  source_dc_code: {c.source_dc_code}\n"
            f"  available_surplus: {c.available_surplus} units\n"
            f"  feasible_quantity: {c.feasible_quantity} units\n"
            f"  transit_days: {c.transit_days} days\n"
            f"  route_unit_cost: ${c.route_unit_cost:.2f}/unit\n"
            f"  estimated_total_cost: ${c.estimated_total_cost:.2f}\n"
            f"  can_arrive_before_stockout: {c.can_arrive_before_stockout}"
        )

    candidates_block = "\n\n".join(candidates_formatted)

    prompt = f"""You are a supply-chain fulfillment intelligence recommendation assistant.
Your task is to select the single best candidate source Distribution Center (DC)
to fulfill a stockout risk incident.

INCIDENT CONTEXT:
- Incident Code: {input_data.incident_code}
- Target DC Code: {input_data.target_dc_code}
- Product SKU: {input_data.product_sku}
- Product Name: {input_data.product_name}
- Category: {input_data.category}
- Severity: {input_data.severity}
- Days to Stockout: {input_data.days_to_stockout} days
- Shortage Quantity: {input_data.shortage_qty} units

PRE-VALIDATED FEASIBLE CANDIDATES:
{candidates_block}

MANDATORY INSTRUCTIONS & RESTRICTIONS:
1. Select exactly ONE candidate_id from the supplied candidate list above.
2. Do NOT invent, assume, or select any candidate_id not listed in the candidates block.
3. Do NOT modify transfer quantity, available surplus, transit days, or cost.
4. Do NOT calculate or modify cost or transfer quantity.
5. Provide a clear, professional rationale explaining the selection decision.

OUTPUT FORMAT:
Return a JSON object with exactly two keys:
- "selected_candidate_id": string (must match one candidate_id from the list)
- "rationale": string (brief explanation of the selection decision)
"""
    return prompt
