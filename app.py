import pandas as pd
import streamlit as st

import actions
import ui_helpers as h

@st.cache_resource
def _scheduler():
    return actions.get_scheduler()


sched = _scheduler()

st.set_page_config(page_title="PartnerGraph", layout="wide")

seeds, profiles, matches = h.load_seeds(), h.load_profiles(), h.load_matches()
by_name = {h.company_name(m["target_key"], seeds, profiles): m for m in matches}

st.title("PartnerGraph")
st.caption("Your personal BD agent: finds customers and partners from real website evidence, "
           "then reaches out when you approve.")

# ---- sidebar: founder profile (persisted to data/me.json; stable keys, seeded once from the file)
saved = h.load_me()
for k, v in saved.items():
    st.session_state.setdefault(f"me_{k}", v)
with st.sidebar:
    st.subheader("Founder profile")
    st.text_input("Name", key="me_name")
    st.text_input("Company URL", key="me_company_url")
    st.radio("Goal", list(h.GOALS), key="me_goal")
    st.radio("Email tone", h.TONES, key="me_tone")
    me = {k: st.session_state[f"me_{k}"] for k in saved}
    if me != saved:
        h.save_me(me)
    if st.button("Reload results"):
        st.rerun()  # script re-reads the JSON files on every run

score_col = h.GOALS[me["goal"]]
df = h.ranked_frame(matches, seeds, profiles, sort_col=score_col)
if df.empty:
    st.info("No results yet. Run the pipeline, then click Reload results.")
    st.stop()

who = f"{me['name'].strip()}'s" if me["name"].strip() else "Your"
st.markdown(f"**{who} goal: {me['goal']}. Ranked by {score_col}.**")

styled = df.style.set_properties(subset=[score_col],
                                 **{"background-color": "#fff3bf", "color": "#000", "font-weight": "bold"})
event = st.dataframe(styled, width="stretch", hide_index=True,
                     on_select="rerun", selection_mode="single-row")

rows = event.selection.rows
if not rows:
    st.write("Select a row to see why it's a fit and a draft email.")
    st.stop()

row = df.iloc[rows[0]]
m = by_name[row["company"]]

st.divider()
st.subheader(row["company"])
st.badge(m["type"].upper(), color={"customer": "green", "partner": "blue"}.get(m["type"], "orange"))
c1, c2 = st.columns(2)
c1.metric("Customer score", m["customer_score"])
c2.metric("Partner score", m["partner_score"])

st.markdown("**Why this is a fit for you**")
st.write(h.explanation_text(m) or "Explanation pending")
for ev in m.get("evidence", []):
    st.markdown(f"- {ev['claim']}  \n  [source]({ev['source_url']})")

st.markdown("**Draft email**")
dk = f"{row['company']}|{me['goal']}|{me['tone']}|{me['name']}"  # new draft when inputs change; edits persist otherwise
subject = st.text_input("Subject", value=h.build_subject(me, row["company"]), key=f"subj|{dk}")
body = st.text_area("Body", value=h.build_draft(me, m, profiles, seeds), height=260, key=f"body|{dk}")

if st.button("Approve and send", type="primary"):
    try:
        sent = actions.send_and_record(
            sched, row["company"], m["type"], int(row[score_col]),
            [e["source_url"] for e in m.get("evidence", [])], subject, body)
        st.success(f"Sent at {sent:%H:%M:%S}. Follow-up scheduled.")
    except Exception as e:
        st.error(f"Send failed: {e!r}")

crm_tab, sched_tab = st.tabs(["CRM", "Scheduled"])
with crm_tab:
    st.dataframe(pd.DataFrame(actions.read_crm(), columns=actions.FIELDS), width="stretch", hide_index=True)
with sched_tab:
    st.dataframe(pd.DataFrame(actions.scheduled_jobs(sched), columns=["job_id", "next_run_time"]),
                 width="stretch", hide_index=True)
