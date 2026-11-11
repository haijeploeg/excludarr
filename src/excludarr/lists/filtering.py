"""Apply exclusion conditions without converting unknown facts into false facts."""

from dataclasses import dataclass
from typing import Literal

from excludarr.conditions import All, Evidence, Not, evaluate
from excludarr.facts import Context
from excludarr.list_config import ProxyList
from excludarr.lists.items import ListItem


@dataclass
class ListDecision:
    item: ListItem
    status: Literal["included", "excluded"]
    evidence: list[Evidence]
    unknown: bool = False


def decide(item: ListItem, rule: ProxyList, ctx: Context) -> ListDecision:
    evidence = []
    condition = All([rule.when, *(Not(c) for c in rule.unless)])
    result = evaluate(condition, item, ctx, evidence=evidence)
    status = (
        ("excluded" if rule.on_unknown == "exclude" else "included")
        if result is None
        else "excluded"
        if result
        else "included"
    )
    return ListDecision(item, status, evidence, unknown=result is None)
