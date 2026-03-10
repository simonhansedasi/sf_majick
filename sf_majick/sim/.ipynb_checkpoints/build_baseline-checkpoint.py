   
import pandas as pd
import random
import pickle

from sf_majick.sim.entities import Lead, Opportunity, Account
from sf_majick.sim.reps import SalesRep
from sf_majick.sim.utility_engine import Strategy
from sf_majick.sim.utils import generate_random_leads
from sf_majick import functions as sfmf

# -----------------------------
# Connect to Salesforce
# -----------------------------
sf = sfmf.SalesforceLogin()

# -----------------------------
# Fetch reps/users
# -----------------------------
query_users = "SELECT Id, Name FROM User"
_, df_users = sfmf.run_soql(query_users, sf)
employees = df_users[7:].copy()  # skip first rows if needed

reps = []
for _, row in employees.iterrows():
    rep = SalesRep(
        id=row['Id'],
        strategy=None
    )
    reps.append(rep)

# -----------------------------
# Assign strategies
# -----------------------------
rep_strategies = [
    Strategy("Whale Hunter", risk_aversion=1.0, communicativeness=0.5, patience=0.7, focus=0.8, momentum_bias=0.6),
    Strategy("Volume Chaser", risk_aversion=0.0, communicativeness=0.8, patience=0.3, focus=0.3, momentum_bias=0.2),
    Strategy("Momentum Follower", risk_aversion=0.5, communicativeness=0.6, patience=0.5, focus=0.5, momentum_bias=1.0),
    Strategy("Steady Closer", risk_aversion=0.5, communicativeness=0.4, patience=0.8, focus=0.7, momentum_bias=0.3),
]

for rep, strat in zip(reps, rep_strategies):
    rep.strategy = strat

# -----------------------------
# Fetch Contacts to seed Leads
# -----------------------------
query = '''
    SELECT Id, OwnerId, Name
    FROM Account
'''

record_acc, df_acc = sfmf.run_soql(query, sf)



accounts = []

for _, row in df_acc.iterrows():
    account = Account(
        id=row['Id'],
        name=row['Name'],
        annual_revenue=row.get('AnnualRevenue', random.randint(50_000, 5_000_000)),
        rep_id=random.choice(reps).id
    )
    
    # Assign to a rep — simple random assignment for now
    account.owner_id = random.choice(reps).id
    accounts.append(account)












# Generate initial leads from Salesforce contacts
leads = []
# Optionally generate extra random leads
leads.extend(generate_random_leads(n=4))

# -----------------------------
# Generate initial Opportunities (no Account object)
# -----------------------------

opportunities = []
for acc in accounts:  # seed first few accounts
    opp = acc.create_opportunity()
    opportunities.append(opp)

# -----------------------------
# Save baseline
# -----------------------------
state = {
    "reps": reps,
    "leads": leads,
    "opportunities": opportunities,
    'accounts': accounts
}

with open("data/baseline_state.pkl", "wb") as f:
    pickle.dump(state, f)

print(f"Baseline saved. Reps: {len(reps)}, Leads: {len(leads)}, Opportunities: {len(opportunities)},  accounts: {len(accounts)}")

