"""Deterministic cross-generation convergence and reporting."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .discovery import canonical_digest


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def generation_chain(run_dir: Path) -> list[Path]:
    """Return a validated generation-zero-through-current run chain."""
    chain: list[Path] = []
    current = run_dir.resolve()
    seen: set[Path] = set()
    while True:
        if current in seen:
            raise ValueError("generation lineage contains a cycle")
        seen.add(current)
        chain.append(current)
        context = current / "generation-context.json"
        if not context.is_file():
            break
        value = _read(context)
        current = Path(value["parent_run"]).resolve(strict=True)
    chain.reverse()
    generations = [_read(path / "pareto-archive.json")["generation"] for path in chain]
    if generations != list(range(generations[-1] + 1)):
        raise ValueError("generation lineage must be contiguous from generation zero")
    return chain


def _axes(row: Mapping[str, Any]) -> tuple[int, int, int]:
    lcb = row.get("fidelity_lcb")
    decisions = row.get("median_material_decisions")
    size = row.get("skill_bytes")
    if not isinstance(lcb, (int, float)) or not 0 <= lcb <= 1:
        raise ValueError("candidate fidelity LCB is invalid")
    if not isinstance(decisions, (int, float)) or decisions < 0:
        raise ValueError("candidate decision median is invalid")
    if not isinstance(size, int) or size < 1:
        raise ValueError("candidate skill size is invalid")
    return round(lcb * 1_000_000), round(decisions * 1_000), size


def convergence_decision(run_dir: Path, policy: Mapping[str, Any], *,
                         effective_candidates: int, terminal_cells: int,
                         expected_cells: int) -> dict[str, Any]:
    chain = generation_chain(run_dir)
    generation = len(chain) - 1
    policy_digest = canonical_digest(policy)
    eps_lcb = int(policy["fidelity_epsilon_ppm"])
    eps_decisions = int(policy["decision_epsilon_milli"])
    eps_bytes = int(policy["skill_bytes_epsilon"])
    transitions: list[dict[str, Any]] = []
    historical: list[tuple[int, Mapping[str, Any]]] = []
    history: list[dict[str, Any]] = []
    for index, path in enumerate(chain):
        archive_path = path / "pareto-archive.json"
        archive = _read(archive_path)
        rows = {row["candidate_id"]: row for row in archive["candidates"]}
        ids = archive["archive"]
        if not ids or any(candidate_id not in rows for candidate_id in ids):
            raise ValueError("Pareto archive candidate inventory is invalid")
        history.append({
            "generation": index,
            "pareto_archive_digest": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        })
        if index:
            covered: list[dict[str, Any]] = []
            novel: list[str] = []
            for candidate_id in ids:
                current_axes = _axes(rows[candidate_id])
                cover = None
                for prior_generation, prior in historical:
                    prior_axes = _axes(prior)
                    if (prior_axes[0] >= current_axes[0] - eps_lcb
                            and prior_axes[1] <= current_axes[1] + eps_decisions
                            and prior_axes[2] <= current_axes[2] + eps_bytes):
                        cover = {"candidate_id": candidate_id,
                                 "covered_by": prior["candidate_id"],
                                 "covered_by_generation": prior_generation}
                        break
                if cover is None:
                    novel.append(candidate_id)
                else:
                    covered.append(cover)
            transitions.append({"generation": index, "novel_frontier": bool(novel),
                                "novel_candidates": novel, "covered_candidates": covered})
        historical.extend((index, rows[candidate_id]) for candidate_id in ids)
    streak = 0
    for transition in reversed(transitions):
        if transition["novel_frontier"]:
            break
        streak += 1
    full_inventory = (effective_candidates == int(policy["full_candidate_count"])
                      and terminal_cells == expected_cells)
    eligible = full_inventory or not bool(policy["require_full_candidate_inventory"])
    limit = generation >= int(policy["maximum_generation"])
    stagnated = (eligible and generation >= int(policy["minimum_generation"])
                 and streak >= int(policy["patience"]));
    stop = limit or stagnated
    return {
        "schema": "DiscoveryConvergenceDecision.v1", "generation": generation,
        "policy_digest": policy_digest, "eligible": eligible,
        "history": history, "transitions": transitions,
        "consecutive_stagnant_generations": streak,
        "converged": stagnated, "stop": stop,
        "reason": "generation-limit" if limit else (
            "frontier-stagnation" if stagnated else "continue"),
    }


def _candidate_theme(run_dir: Path, candidate_id: str) -> str:
    archive = _read(run_dir / "pareto-archive.json")
    if archive["generation"] == 0:
        return "minimal-seed" if candidate_id == "g00-c00" else "independent-seed-variant"
    lineage_path = run_dir / "candidate-lineage.json"
    if not lineage_path.is_file():
        return "legacy-unbound"
    lineage = _read(lineage_path)
    match = next((row for row in lineage.get("candidates", ())
                  if row.get("candidate_id") == candidate_id), None)
    return match.get("mutation_intent_id", "legacy-unbound") if match else "legacy-unbound"


def _theme_details(theme: str, catalog: Mapping[str, Mapping[str, str]]) -> tuple[str, str]:
    built_in = {
        "minimal-seed": ("Minimal seed", "Original minimal interview seed; no mutation applied."),
        "independent-seed-variant": (
            "Independent seed variant",
            "Generated independently from the same minimal seed without train feedback."),
        "legacy-unbound": (
            "Legacy unbound evolution",
            "Evolved from its parent using train feedback, but without a bound structural direction."),
    }
    if theme in built_in:
        return built_in[theme]
    value = catalog.get(theme, {})
    return value.get("label", theme), value.get("directive", "No description recorded.")


def _skill_summary(run_dir: Path, candidate_id: str, limit: int = 320) -> str:
    text = (run_dir / "candidates" / candidate_id / "SKILL.md").read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in text.splitlines()
                  if line.startswith("# ")), candidate_id)
    description = next((line.split(":", 1)[1].strip() for line in text.splitlines()
                        if line.startswith(("description:", "_description:"))), "")
    summary = f"{title} — {description}" if description else title
    return summary if len(summary) <= limit else summary[:limit - 1].rstrip() + "…"


def comparison_payload(parent_run: Path, run_dir: Path,
                       convergence: Mapping[str, Any],
                       mutation_catalog: Mapping[str, Mapping[str, str]] | None = None,
                       skill_summaries: Mapping[str, Mapping[str, str]] | None = None,
                       ) -> dict[str, Any]:
    parent_archive = _read(parent_run / "pareto-archive.json")
    current_archive = _read(run_dir / "pareto-archive.json")
    lineage = _read(run_dir / "candidate-lineage.json")
    parent_rows = {row["candidate_id"]: row for row in parent_archive["candidates"]}
    current_rows = {row["candidate_id"]: row for row in current_archive["candidates"]}
    candidates = []
    for link in lineage["candidates"]:
        child = current_rows[link["candidate_id"]]
        parent = parent_rows[link["parent_candidate_id"]]
        mutation_theme = link.get("mutation_intent_id", "legacy-unbound")
        catalog = mutation_catalog or {}
        mutation_label, mutation_description = _theme_details(mutation_theme, catalog)
        parent_theme = _candidate_theme(parent_run, link["parent_candidate_id"])
        parent_label, parent_description = _theme_details(parent_theme, catalog)
        generated = (skill_summaries or {}).get(link["candidate_id"], {})
        candidates.append({
            "candidate_id": link["candidate_id"],
            "parent_candidate_id": link["parent_candidate_id"],
            "parent_skill_summary": generated.get("parent_summary") or _skill_summary(
                parent_run, link["parent_candidate_id"]),
            "candidate_skill_summary": generated.get("candidate_summary") or _skill_summary(
                run_dir, link["candidate_id"]),
            "skill_change_summary": generated.get(
                "change_summary", "No LLM-authored change summary is available for this legacy run."),
            "mutation_intent_id": mutation_theme,
            "mutation_intent_label": mutation_label,
            "mutation_directive": mutation_description,
            "parent_mutation_theme": parent_theme,
            "parent_mutation_label": parent_label,
            "parent_mutation_description": parent_description,
            "fidelity_lcb": child["fidelity_lcb"],
            "fidelity_lcb_delta": child["fidelity_lcb"] - parent["fidelity_lcb"],
            "median_material_decisions": child["median_material_decisions"],
            "decision_delta": (child["median_material_decisions"]
                               - parent["median_material_decisions"]),
            "skill_bytes": child["skill_bytes"],
            "skill_bytes_delta": child["skill_bytes"] - parent["skill_bytes"],
            "pareto": link["candidate_id"] in current_archive["archive"],
        })
    def state_stats(path: Path) -> dict[str, int]:
        state = _read(path / "state.json")["cells"].values()
        return {"terminal": len(state),
                "invalid": sum(row["status"] == "invalid" for row in state),
                "retried": sum(row["attempts"] == 2 for row in state)}
    parent_feedback = _read(parent_run / "generation-feedback.json")
    current_feedback = _read(run_dir / "generation-feedback.json")
    before = set(parent_feedback["root_causes"]); after = set(current_feedback["root_causes"])
    return {
        "schema": "DiscoveryGenerationComparison.v1",
        "parent_generation": parent_archive["generation"],
        "generation": current_archive["generation"],
        "parent_archive": parent_archive["archive"],
        "current_archive": current_archive["archive"],
        "parent_stats": state_stats(parent_run), "current_stats": state_stats(run_dir),
        "best_lcb_parent": max(row["fidelity_lcb"] for row in parent_rows.values()),
        "best_lcb_current": max(row["fidelity_lcb"] for row in current_rows.values()),
        "candidates": candidates,
        "root_causes": {"persisted": sorted(before & after), "new": sorted(after - before),
                        "resolved": sorted(before - after)},
        "convergence": dict(convergence),
    }


def render_comparison_html(payload: Mapping[str, Any]) -> str:
    e = lambda value: html.escape(str(value), quote=True)
    rows = ""
    for row in sorted(payload["candidates"], key=lambda item: item["candidate_id"]):
        parent_story = (f"<b>{e(row['parent_mutation_label'])}</b><br>"
                        f"<small>{e(row['parent_mutation_description'])}</small>")
        mutation_story = (f"<b>{e(row['mutation_intent_label'])}</b><br>"
                          f"<small>{e(row['mutation_directive'])}</small>")
        values = (f"<td>{e(row['candidate_id'])}</td>",
                  f"<td>{e(row['parent_candidate_id'])}</td>",
                  f"<td><small>{e(row['parent_skill_summary'])}</small></td>",
                  f"<td><small>{e(row['candidate_skill_summary'])}</small></td>",
                  f"<td><small>{e(row['skill_change_summary'])}</small></td>",
                  f"<td>{parent_story}</td>", f"<td>{mutation_story}</td>",
                  f"<td>{e(f'{row['fidelity_lcb']:.6f}')}</td>",
                  f"<td>{e(f'{row['fidelity_lcb_delta']:+.6f}')}</td>",
                  f"<td>{e(f'{row['median_material_decisions']:.1f}')}</td>",
                  f"<td>{e(f'{row['decision_delta']:+.1f}')}</td>",
                  f"<td>{e(row['skill_bytes'])}</td>",
                  f"<td>{e(f'{row['skill_bytes_delta']:+d}')}</td>",
                  f"<td>{'yes' if row['pareto'] else 'no'}</td>")
        rows += "<tr>" + "".join(values) + "</tr>"
    causes = payload["root_causes"]
    cause_html = "".join(
        f"<h3>{e(label.title())}</h3><p>{e(', '.join(causes[label]) or 'none')}</p>"
        for label in ("persisted", "new", "resolved"))
    convergence = payload["convergence"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Generation {e(payload['parent_generation'])} to {e(payload['generation'])}</title>
<style>body{{font:14px system-ui;margin:2rem;color:#17202a}}table{{border-collapse:collapse;width:100%;min-width:1750px}}th,td{{border:1px solid #ccd;padding:.55rem;text-align:right;vertical-align:top}}th:nth-child(-n+7),td:nth-child(-n+7){{text-align:left}}small{{display:block;max-width:26rem;line-height:1.35;color:#465}}.table-wrap{{overflow-x:auto}}.cards{{display:flex;gap:1rem}}.card{{border:1px solid #ccd;padding:1rem;flex:1}}code{{background:#eef;padding:.15rem}}</style></head>
<body><h1>Generation {e(payload['parent_generation'])} → {e(payload['generation'])}</h1>
<div class="cards"><div class="card"><b>Best fidelity LCB</b><br>{e(f"{payload['best_lcb_parent']:.6f}")} → {e(f"{payload['best_lcb_current']:.6f}")}</div>
<div class="card"><b>Invalid cells</b><br>{e(payload['parent_stats']['invalid'])} → {e(payload['current_stats']['invalid'])}</div>
<div class="card"><b>Retries</b><br>{e(payload['parent_stats']['retried'])} → {e(payload['current_stats']['retried'])}</div></div>
<h2>Lineage comparison</h2><div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Parent</th><th>Parent skill in brief</th><th>Candidate skill in brief</th><th>Skill content change</th><th>How the parent was created</th><th>What changed for this candidate</th><th>LCB</th><th>Δ LCB</th><th>Decisions</th><th>Δ decisions</th><th>Bytes</th><th>Δ bytes</th><th>Pareto</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Train root causes</h2>{cause_html}
<h2>Convergence</h2><p><b>{e(convergence['reason'])}</b>; stagnant transitions: {e(convergence['consecutive_stagnant_generations'])}; stop: {e(convergence['stop'])}</p>
</body></html>\n"""


def write_comparison_report(parent_run: Path, run_dir: Path,
                            convergence: Mapping[str, Any],
                            mutation_catalog: Mapping[str, Mapping[str, str]] | None = None,
                            skill_summaries: Mapping[str, Mapping[str, str]] | None = None) -> str:
    """Write deterministic JSON and self-contained HTML comparison artifacts."""
    payload = comparison_payload(parent_run, run_dir, convergence, mutation_catalog,
                                 skill_summaries)
    json_path = run_dir / "generation-comparison.json"
    temporary = json_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(json_path)
    html_path = run_dir / "generation-comparison.html"
    temporary_html = html_path.with_suffix(".html.tmp")
    temporary_html.write_text(render_comparison_html(payload), encoding="utf-8")
    temporary_html.replace(html_path)
    return hashlib.sha256(html_path.read_bytes()).hexdigest()


__all__ = ["comparison_payload", "convergence_decision", "generation_chain",
           "render_comparison_html", "write_comparison_report"]
