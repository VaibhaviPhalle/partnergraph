# PartnerGraph

**A personal business development agent for solo founders.** PartnerGraph reads company websites, finds who has the problem you solve (customers) and who serves the same buyers with a complementary product (partners), proves every match with source links, and sends outreach once you approve it.

Built solo at the Personal Agents Hackathon (tokens&, AWS Builder Loft SF, Nov 20 2026).

> For the demo, PartnerGraph found PartnerGraph's own first customers and partners.

## The problem

Solo founders can't afford a business development hire, meaning someone to research companies, find customers and partners, and reach out. Lead tools like Clay, Apollo and Common Room give you a contact database and a black-box score, and they only look for leads. A founder still has to work out why a company fits, whether they'd make a better partner than customer, and what to say.

## What it does

1. **Reads.** It crawls 6 to 9 pages per company (home, product, blog, careers, job posts, integrations) and caches them locally.
2. **Understands.** Gemini extracts a structured profile per company: capabilities, problems, segments, tech stack, and signals. Every signal keeps a verbatim quote and its source URL.
3. **Connects.** Profiles go into a cognee knowledge graph, which links your problems to the companies that show them.
4. **Scores.** Plain Python, no LLM, gives each target a customer score and a partner score. Every point traces back to a link.
5. **Explains.** The agent writes why each match fits, citing only URLs it actually crawled. A validator removes any URL it didn't crawl.
6. **Acts.** It drafts an email in your voice that cites one real signal. You edit it and approve it, then it sends over Gmail, logs a CRM row, and schedules a follow-up.

## End-to-end pipeline

Each box says what happens and what comes out of it.

```mermaid
flowchart TD
    subgraph IN["📥 1. INPUT · what the founder gives"]
        A["👤 Founder profile<br/>name · company · goal · email tone"]
        B["🌐 Target list<br/>company URLs in seeds.json"]
    end

    subgraph READ["🕷️ 2. READ · crawl.py"]
        C["Fetch up to 8 pages per company<br/>home · product · blog · careers · integrations<br/>+ job posts via Greenhouse / Ashby APIs"]
        D[("💾 Page cache · data/raw<br/>url · page type · clean text")]
    end

    subgraph UNDERSTAND["🧠 3. UNDERSTAND · extract.py + Gemini"]
        E["Extract MY company first<br/>→ the problems I solve<br/>= shared vocabulary"]
        F["Extract each target with that vocabulary<br/>→ signal = problem id + quote + source URL"]
        G[("📄 Profiles · data/profiles")]
    end

    subgraph CONNECT["🕸️ 4. CONNECT · cognee"]
        H[("Knowledge graph<br/>Me → SOLVES → Problem ← SIGNALS ← Target<br/>Me → SERVES → Segment ← SERVES ← Target")]
    end

    subgraph DECIDE["⚖️ 5. DECIDE · score.py + explain.py"]
        I["🛒 Customer score<br/>job 3 · blog 2 · product 1 · integration 1"]
        J["🤝 Partner score<br/>integration 40 · segment 30 · tech 30"]
        K["💬 Explanation<br/>why this is a fit"]
        L[("🏆 matches.json<br/>type · scores · evidence · explanation")]
    end

    subgraph ACT["🚀 6. ACT · Streamlit app"]
        M["📊 Ranked list<br/>sorted by the founder's goal"]
        N["🔗 Evidence panel<br/>every claim links to its page"]
        O["✉️ Draft email<br/>founder's voice · cites one signal"]
        P{"✅ Founder<br/>approves?"}
        Q["📤 Send via Gmail SMTP"]
        R[("📇 crm.csv<br/>status: sent")]
        S["⏰ Follow-up<br/>APScheduler · +3 days"]
    end

    N1>"📝 Demo runs offline from this cache"]
    N2>"📝 Signals citing uncrawled URLs are dropped"]
    N3>"📝 No LLM in scoring: plain math you can check"]
    N4>"📝 Validator removes any URL that wasn't crawled"]
    N5>"📝 Human in the loop: nothing sends without approval"]

    B --> C --> D
    D --> E --> F --> G
    G --> H
    G --> I
    G --> J
    H --> K
    I --> L
    J --> L
    K --> L
    A --> M
    L --> M --> N --> O --> P
    P -- "yes" --> Q --> R
    Q --> S
    P -- "edit" --> O

    D -.- N1
    F -.- N2
    I -.- N3
    K -.- N4
    P -.- N5

    classDef input fill:#E3F2FD,stroke:#1565C0,color:#0D47A1,stroke-width:2px
    classDef read fill:#F3E5F5,stroke:#6A1B9A,color:#4A148C,stroke-width:2px
    classDef llm fill:#FFF3E0,stroke:#E65100,color:#BF360C,stroke-width:2px
    classDef graphc fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20,stroke-width:2px
    classDef decide fill:#FFFDE7,stroke:#F9A825,color:#5D4037,stroke-width:2px
    classDef act fill:#FCE4EC,stroke:#AD1457,color:#880E4F,stroke-width:2px
    classDef gate fill:#FFEBEE,stroke:#C62828,color:#B71C1C,stroke-width:3px
    classDef note fill:#FAFAFA,stroke:#9E9E9E,color:#424242,stroke-dasharray:4 3

    class A,B input
    class C,D read
    class E,F,G llm
    class H graphc
    class I,J,K,L decide
    class M,N,O,Q,R,S act
    class P gate
    class N1,N2,N3,N4,N5 note

    style IN fill:#F5FAFF,stroke:#1565C0
    style READ fill:#FBF5FC,stroke:#6A1B9A
    style UNDERSTAND fill:#FFFBF5,stroke:#E65100
    style CONNECT fill:#F5FBF5,stroke:#2E7D32
    style DECIDE fill:#FFFEF5,stroke:#F9A825
    style ACT fill:#FFF5F8,stroke:#AD1457
```

## Worked example: one match, start to finish

How the agent decides MongoDB is a partner for PartnerGraph, and what it does about it.

```mermaid
flowchart TD
    U1["📥 INPUT<br/>my company: PartnerGraph<br/>target: https://www.mongodb.com"]
    U2["🕷️ READ<br/>crawler caches<br/>https://www.mongodb.com/partners"]
    U3["🧠 MY SIDE<br/>PartnerGraph solves:<br/>finding_partners · finding_customers<br/>partnership_program_scaling"]
    U4["🧠 THEIR SIDE<br/>partners page shows a large partner program<br/>signal: partnership_program_scaling<br/>source: mongodb.com/partners"]
    U5[("🕸️ COGNEE GRAPH<br/>PartnerGraph → SOLVES → partnership_program_scaling<br/>MongoDB → SIGNALS → partnership_program_scaling")]
    U6["⚖️ DECIDE<br/>matching signal → customer points<br/>shared segments + tech → partner points<br/>type = higher score"]
    U7["💬 EXPLAIN<br/>MongoDB runs a partner program at scale,<br/>the problem PartnerGraph solves.<br/>Source: mongodb.com/partners"]
    U8["✉️ DRAFT<br/>Hi MongoDB team, I saw your partner program<br/>at mongodb.com/partners ...<br/>Vaibhavi, founder of PartnerGraph"]
    U9{"✅ Vaibhavi<br/>approves"}
    U10["📤 SENT via Gmail<br/>📇 crm.csv: mongodb · partner · score · link · sent<br/>⏰ follow-up in 3 days"]

    URL(["🔗 https://www.mongodb.com/partners<br/>the same link at every step"])

    T1>"📝 Raw HTML becomes clean cached text"]
    T2>"📝 Quote kept verbatim, URL must be crawled"]
    T3>"📝 Plain math, every point traces to a link"]
    T4>"📝 Founder can edit before sending"]

    U1 --> U2 --> U3 --> U4 --> U5 --> U6 --> U7 --> U8 --> U9 --> U10

    URL -.-> U2
    URL -.-> U4
    URL -.-> U5
    URL -.-> U7
    URL -.-> U8

    U2 -.- T1
    U4 -.- T2
    U6 -.- T3
    U9 -.- T4

    classDef input fill:#E3F2FD,stroke:#1565C0,color:#0D47A1,stroke-width:2px
    classDef read fill:#F3E5F5,stroke:#6A1B9A,color:#4A148C,stroke-width:2px
    classDef llm fill:#FFF3E0,stroke:#E65100,color:#BF360C,stroke-width:2px
    classDef graphc fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20,stroke-width:2px
    classDef decide fill:#FFFDE7,stroke:#F9A825,color:#5D4037,stroke-width:2px
    classDef act fill:#FCE4EC,stroke:#AD1457,color:#880E4F,stroke-width:2px
    classDef gate fill:#FFEBEE,stroke:#C62828,color:#B71C1C,stroke-width:3px
    classDef url fill:#E0F7FA,stroke:#00838F,color:#006064,stroke-width:3px
    classDef note fill:#FAFAFA,stroke:#9E9E9E,color:#424242,stroke-dasharray:4 3

    class U1 input
    class U2 read
    class U3,U4 llm
    class U5 graphc
    class U6,U7 decide
    class U8,U10 act
    class U9 gate
    class URL url
    class T1,T2,T3,T4 note

    linkStyle 9,10,11,12,13 stroke:#00838F,stroke-width:2px,stroke-dasharray:6 4
```

**Color key:** 🔵 input · 🟣 crawl · 🟠 LLM extraction · 🟢 cognee graph · 🟡 scoring · 🩷 actions · 🔴 human approval · 🩵 the evidence link

The same link, `https://www.mongodb.com/partners`, travels through every step: it's crawled, becomes a signal, becomes a graph edge, adds to the score, is cited in the explanation, and is cited in the email. That's the evidence path.

## Knowledge graph schema

```
Me        --OFFERS-->         Capability --SOLVES--> Problem
Target    --HAS_SIGNAL-->     Problem
Signal    --FOUND_ON-->       SourceURL
Target    --SERVES-->         Segment   <--SERVES--  Me
Target    --USES-->           TechStack <--USES--    Me
```

**Customer path:** I solve problem X, and the target shows problem X in a job post, so the target is a likely customer. The job post URL is the proof.

**Partner path:** we serve the same segment and use the same tools, but sell different products, so we're a likely integration or referral partner.

## Scoring

**Customer score (0 to 100):** each target signal that matches one of my problems earns points: job post 3, blog post 2, product page 1, integrations page 1. The score is points / 8 x 100, capped at 100. A job post is weighted highest because hiring for a problem means they are spending money on it.

**Partner score (0 to 90):** an integration link between the two companies earns 40, segment overlap earns up to 30, and tech overlap earns up to 30. The total is scaled so the best partner in the batch gets 90.

If both scores are 50 or more, the type is "both". Otherwise it's whichever score is higher.

The LLM never sets a score. It only reads pages and writes explanations.

## Personal agent features

- **Founder profile:** name, company, goal (find customers or find partners), and email tone.
- **Goal-aware ranking:** switching the goal re-ranks the list.
- **Drafts in your voice:** first person, signed with your name, citing one real signal.
- **Human in the loop:** nothing sends until you approve.
- **Real actions:** a Gmail send, a CRM row, and a scheduled follow-up.

## Tech stack

Python 3.11, requests, BeautifulSoup, Pydantic, litellm with Gemini, cognee Cloud, Streamlit, APScheduler with SQLite job store, smtplib.

## Run it

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys below

python crawl.py                          # cache target pages
python run_pipeline.py --refresh         # extract, score, explain
streamlit run app.py                     # open http://localhost:8501
```

`.env` keys:

```
COGNEE_SERVICE_URL=    # your cognee tenant URL
COGNEE_API_KEY=
GEMINI_API_KEY=
EXTRACT_MODEL=gemini/gemini-3.5-flash
MY_COMPANY_KEY=partnergraph
GMAIL_USER=
GMAIL_APP_PASSWORD=    # 16-char Gmail app password
DEMO_TO_EMAIL=
FOLLOWUP_MINUTES=2     # demo only; default is 3 days
```

## Design decisions

- **Deterministic scores:** judges and users can check every point against a link.
- **Controlled vocabulary:** my problems are extracted first and passed into every target extraction, so "ETL failures" and "pipeline reliability" map to the same problem ID and actually match.
- **Offline demo:** pages, profiles and explanations are cached, so the UI never calls the network until you hit send.
- **Validated citations:** explanations and emails can only cite URLs that were actually crawled.

## How it compares

| | Clay / Apollo / Common Room | PartnerGraph |
|---|---|---|
| User | Sales teams | One founder |
| Output | Contact list and score | Ranked customers and partners |
| Why | Black box | Evidence path with source links |
| Partners | No | Yes |
| Outreach | You write it | Drafted from a real signal, sent after approval |

## Roadmap

- Target discovery: "find 50 logistics companies in California"
- Fixed-scale partner score instead of batch-relative
- Continuous site monitoring that re-drafts outreach when a new signal appears
- Reply detection and multi-touch sequences
- LinkedIn and news signals
- HubSpot and Salesforce sync
- Gmail history check: follow up instead of cold-emailing someone you already talk to

## Author

Vaibhavi Phalle, backend engineer (FastAPI, Kafka, DAG orchestration, RAG).
