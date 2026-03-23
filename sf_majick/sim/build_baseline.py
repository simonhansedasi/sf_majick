import pandas as pd
import random
import pickle

from sf_majick.sim.entities import Lead, Opportunity, Account
from sf_majick.sim.reps import SalesRep, ARCHETYPE_ROTATION
from sf_majick.sim.utils import generate_random_leads
from sf_majick import functions as sfmf

# Strategy is derived automatically from archetype via Strategy.from_personality()
# in SalesRep.__post_init__ — no manual knob assignment needed here.

ARCHETYPE_ROTATION = ["Closer", "Nurturer", "Grinder", "Scattered"]


# ------------------------------------------------------------------
# Connect to Salesforce
# ------------------------------------------------------------------
sf = sfmf.SalesforceLogin()


# ------------------------------------------------------------------
# Fetch reps/users and assign archetypes
# ------------------------------------------------------------------
query_users = "SELECT Id, Name FROM User"
_, df_users = sfmf.run_soql(query_users, sf)
employees = df_users[7:].copy()

reps = []
for i, (_, row) in enumerate(employees.iterrows()):
    archetype_name = ARCHETYPE_ROTATION[i % len(ARCHETYPE_ROTATION)]

    rep = SalesRep(
        id=row["Id"],
        archetype_name=archetype_name,
        # strategy derives automatically from archetype in __post_init__
    )
    reps.append(rep)
    print(f"  Rep {row['Name']!r:30s} → archetype={archetype_name}, strategy={rep.strategy.name!r}")

print(f"\nTotal reps: {len(reps)}")


# ------------------------------------------------------------------
# Fetch Accounts and assign to reps
# ------------------------------------------------------------------
query_acc = "SELECT Id, Name, AnnualRevenue, OwnerId FROM Account"
_, df_acc = sfmf.run_soql(query_acc, sf)

sf_owner_to_rep = {rep.id: rep for rep in reps}

accounts = []
for _, row in df_acc.iterrows():
    sf_owner_id  = row.get("OwnerId", None)
    assigned_rep = sf_owner_to_rep.get(sf_owner_id, random.choice(reps))

    account = Account(
        id=row["Id"],
        name=row["Name"],
        annual_revenue=row.get("AnnualRevenue") or random.randint(50_000, 5_000_000),
        rep_id=assigned_rep.id,
    )
    accounts.append(account)

print(f"Total accounts: {len(accounts)}")


# ------------------------------------------------------------------
# Seed leads
# ------------------------------------------------------------------
leads = []
leads.extend(generate_random_leads(n=4))
print(f"Total leads: {len(leads)}")


# ------------------------------------------------------------------
# Generate initial Opportunities
# ------------------------------------------------------------------
opportunities = []
for acc in accounts:
    opp = acc.create_opportunity()
    opportunities.append(opp)

print(f"Total opportunities: {len(opportunities)}")


# ------------------------------------------------------------------
# Save baseline
# ------------------------------------------------------------------
state = {
    "reps":          reps,
    "leads":         leads,
    "opportunities": opportunities,
    "accounts":      accounts,
}

with open("data/baseline_state.pkl", "wb") as f:
    pickle.dump(state, f)

print(
    f"\nBaseline saved → "
    f"reps={len(reps)}, leads={len(leads)}, "
    f"opportunities={len(opportunities)}, accounts={len(accounts)}"
)
