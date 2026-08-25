# Home Server sticky safety

The repository-root `AGENTS.md` is authoritative. Before any repository write,
commit, push, pull-request action, merge, live cluster or host mutation,
application-state mutation, external/provider mutation, credential action, or
destructive action, re-read and obey its **Non-negotiable rules**,
**Authorization boundaries**, and **Unsupported operations and hard stops**.

Permission in one plane never implies permission in another. If `AGENTS.md`
cannot be read or conflicts with an authoritative operator manual, stop and
report the discrepancy. Discovery grants no authority.
