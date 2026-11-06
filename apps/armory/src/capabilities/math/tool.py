"""Read-only MCP and slash-command entry for isolated mathematics."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from src.capabilities.math import domain
from src.capabilities.math.contract import (BatchResult, Binding, CalculusOptions, ContinuationInput,
                                            MatrixOptions, RootEquation, SolveResult, TableFormulaInput)
from src.commands import command
from src.server import mcp


@command(name="solve", description="Calculate an expression or solve recursive equation constraints")
@mcp.tool(
    meta={
        "keywords": ["math", "mathematics", "calculate", "equation", "solve", "algebra", "arithmetic", "complex", "formula"],
        "display_label": "Solving equations",
        "ai_explain_result": True,
    },
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def tool_math_solve(
    equation: Annotated[RootEquation, Field(
        description=("Expression/equality string, e.g. y = m * b / 2 + x, or object with expression, solve_for, domain (real/complex), "
                     "precision (15–100), method (symbolic/auto/numeric/certified), assumptions, split_cases, units/output_units, trace, and numerical hints. "
                     "expression may be a list of equalities. Certified mode supports exact real rational-polynomial roots. "
                     "Numerical searches need supplied hints and return partial approximate roots. Use explicit multiplication; complex numbers use i/I."),
    )],
    data: Annotated[list[Binding], Field(
        description=(
            "Bindings; use [] when none. Constant: {type:'constant',name:'m',value:5}. "
            "Reference: {type:'variable',name:'x',value:'m'}. "
            "Nested equation: {type:'equation',name:'b',value:{equation:'b = (p + 4) / q',data:[...]}}. "
            "Nested data inherits parent bindings and may shadow helper names. Unknowns and circular equations are solved together."
        ),
        max_length=64,
    )],
) -> SolveResult:
    """Evaluate arithmetic or solve equations over complex numbers, preserving all
    solution branches and free parameters. Supported syntax: + - * / ^ **,
    parentheses, sin/cos/tan, inverse/hyperbolic variants, exp/log/sqrt/abs,
    constants pi, E, i/I. Return exact values and numeric approximations.
    Optional structured equation controls targets, domain, precision, numerical
    search, and calculation trace. Verification describes candidate checks;
    completeness separately states whether additional solutions may exist.
    Parametric results retain conditions; unresolved or timeout results do not
    establish absence of solutions. No input is executed as code or stored.
    """
    return await domain.desk.solve(equation, data)


@command(name="batch", description="Evaluate the same formula over independent records")
@mcp.tool(
    meta={"keywords": ["math", "batch", "formula", "records", "calculate", "table", "equation"],
          "display_label": "Calculating formula records", "ai_explain_result": True},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
)
async def tool_math_batch(
    equation: Annotated[RootEquation, Field(description="Shared equation string or structured controls, exactly as tool_math_solve accepts.")],
    data: Annotated[list[Any], Field(min_length=1, max_length=32, description=(
        "Independent records: [{id:'row1',data:[{type:'constant',name:'x',value:5}]}]. "
        "Each record has its own recursive data bindings; id is optional. Errors stay local and order is preserved."
    ))],
    ctx: Context,
) -> BatchResult:
    """Evaluate a formula or system for up to 32 records with two active workers.
    Return each record's solutions, verification, and diagnostics. Mathematical
    inconsistency is a valid per-record answer. A 60-second batch deadline and
    aggregate input/output caps apply; retry unfinished records in smaller batches.
    """
    async def progress(event):
        await ctx.report_progress(event.completed, event.total, event.model_dump_json())
    return await domain.desk.batch(equation, data, progress=progress)


@command(name="continue", description="Continue from one prior result with its conditions and units")
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def tool_math_continue(equation: RootEquation, data: ContinuationInput) -> SolveResult:
    """Reuse a selected prior solution or scalar value. Pass previous result in
    data.previous, select solution_index or slot:value and optional value_name.
    Extra bindings resolve parameters without dropping original restrictions.
    Approximate reuse needs allow_approximate:true and remains partial.
    Opaque conditions cannot be safely reused; supply original problem instead.
    """
    return await domain.desk.continue_from(equation, data)


@command(name="table", description="Apply a formula to an owned attached table page")
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def tool_math_table(equation: RootEquation, data: TableFormulaInput, ctx: Context) -> BatchResult:
    """Map variables to exact numeric column names from an attached table_id.
    data includes columns, shared bindings, offset, and limit (1–32).
    Only current caller's tables are accessible. Raw stored cells bypass display
    rounding. Partial row results stream through MCP progress when requested.
    Follow source.next_offset for remaining rows; missing cells fail per row.
    """
    from src.capabilities.tables.utils import tables
    from src.services.identity_context import current_username

    async def progress(event):
        await ctx.report_progress(event.completed, event.total, event.model_dump_json())
    return await domain.desk.table(equation, data, registry=tables.registry, owner=current_username(), progress=progress)


@command(name="matrix", description="Compute exact bounded matrix operations")
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def tool_math_matrix(
    operation: Literal["add", "subtract", "multiply", "transpose", "determinant", "inverse", "rank", "rref", "solve"],
    data: MatrixOptions,
) -> SolveResult:
    """Calculate with one or two matrices, each at most 8 by 8. Entries are
    finite numbers or restricted numeric constant expressions. data also accepts
    precision and syntax:math/latex. solve interprets matrices as [A,b] for Ax=b.
    Structural operations require exact algebraic entries. Singular systems may
    be inconsistent or parametric; no inverse is returned for singular matrices.
    """
    return await domain.desk.matrix(operation, data)


@command(name="calculus", description="Differentiate or integrate with domain evidence")
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def tool_math_calculus(expression: str, data: CalculusOptions) -> SolveResult:
    """Differentiate (order 1–8) or integrate restricted scalar expressions.
    data includes operation, variable, domain, precision, optional finite real
    bounds, and syntax:math/latex. Indefinite integrals return primitive plus
    integration_constant; retain domain/branch conditions. Definite integrals
    require proven closed-interval continuity; improper integrals unsupported.
    """
    return await domain.desk.calculus(expression, data)
