# Archive – legacy commercial report sections

These modules are **not** imported by the active weekly pipeline. They preserve code removed from the live email for possible reuse.

| File | Historical content |
|------|-------------------|
| `valeur_stabilite_type_client.py` | “Valeur & stabilité par type de client” + stacked PDV-by-type chart |
| `efficacite_commerciale_agent.py` | “Efficacité commerciale par agent” |
| `top5_agents_volume_clients.py` | “Top 5 agents par volume clients” (sort on `Clients_uniques`) |
| `concentration_risque_commercial.py` | “Concentration & risque commercial” |

To reactivate: import these functions from `main` (or merge back into `metrics.py`) and extend the email template.

**Note:** Archived section titles in the table above reflect the **French** copy that appeared in the old email; this README is in English per project convention.
