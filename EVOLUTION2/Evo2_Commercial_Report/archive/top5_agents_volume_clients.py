# Archived – not used by active weekly report. See archive/README.md
from __future__ import annotations

import pandas as pd


def top5_agents_by_volume_clients(agent_df: pd.DataFrame) -> pd.DataFrame:
    """
    Ancienne section 3b : top 5 agents par nombre de clients uniques.
    `agent_df` : sortie de `compute_section3_agents` (archive/efficacite_commerciale_agent.py).
    """
    return agent_df.sort_values("Clients_uniques", ascending=False).head(5)
