# Vuna Livestock — 10-minute demo talking points

**Audience:** farmers, farm managers, finance and accounting staff.
**One-line message:** Vuna Livestock connects the daily work on the farm to stock and accounting in ERPNext, so you can manage your flock and know its value.
**Deck:** `Vuna_Livestock_Talk.pptx` (11 slides; the videos on slides 4, 5, 6, 8 and 9 start automatically).

| Time        | Slide                        | Goal                                   |
| ----------- | ---------------------------- | -------------------------------------- |
| 0:00 – 0:20 | 1. Title                     | Set the promise                        |
| 0:20 – 1:05 | 2. The problem               | Make the pain familiar                 |
| 1:05 – 1:50 | 3. One app inside ERPNext    | Show the scope                         |
| 1:50 – 3:10 | 4. Daily Farm Entry (video)  | Easy data capture                      |
| 3:10 – 3:55 | 5. Traceability (video)      | Full history of every flock            |
| 3:55 – 4:45 | 6. Vet care (video)          | Health records that update value       |
| 4:45 – 5:35 | 7. For finance (IAS 41)      | Costs become asset value               |
| 5:35 – 6:35 | 8. Performance (video)       | Actual vs. target                      |
| 6:35 – 7:20 | 9. Alerts (video)            | Early warnings as tasks                |
| 7:20 – 8:05 | 10. What it means for you    | Benefits for each audience             |
| 8:05 – 10:00| 11. Thank you / Questions    | Q&A                                    |

---

## 1. Title (0:00 – 0:20)

- In ten minutes I'll show you **Vuna Livestock**, a livestock app that runs inside ERPNext.
- The promise is in the title: **manage your flock, and know its value.**
- Everything you'll see is the real application, recorded on our demo farm.

## 2. The problem (0:20 – 1:05)

- **On the farm:** feeding, deaths and egg counts live in notebooks and WhatsApp. Records arrive late, or not at all.
- **For the manager:** rising mortality or slow growth gets noticed weeks later, after the money is lost.
- **In the accounts:** feed and vet costs disappear into expenses, so nobody knows what a growing flock is really worth.
- *Ask the room:* "How many of you have seen a mortality problem only at month-end?"
- **Transition:** Vuna Livestock closes that gap. What happens on the farm flows straight into stock and the books.

## 3. One app, built inside ERPNext (1:05 – 1:50)

- It isn't a separate system. It uses the **stock, accounts, users and approvals you already have**, so there's nothing extra to reconcile.
- It covers six areas:
  1. Daily farm entry
  2. Flocks and individual animals
  3. Vet care
  4. Breeding
  5. **Cost capitalisation (IAS 41)**: point this one out to the finance people.
  6. Performance and alerts
- **Transition:** "Let me show you five of these live."

## 4. Daily Farm Entry (1:50 – 3:10, video 1:18)

Talk over the video:

- **One screen** for the day's work: feeding, deaths, weighing, egg and produce collection, and observations.
- The worker picks the flock once (here **DEMO-FLOCK-001 in House A**) and who did the work.
- Morning feed: **12 kg of layer feed** from the feed store.
- It saves as a **draft**: a supervisor reviews it before any stock moves. Your normal approvals still apply.
- Afternoon: **85 eggs** collected into the produce store.
- The history at the bottom shows every entry and its status.
- **Key message:** these are **standard ERPNext stock entries**, so the accountant never re-types anything.

## 5. Every flock has a life story (3:10 – 3:55)

- Every flock is an ERPNext **Batch**. It knows its **age**, its **house** and its **capitalisation period**.
- One click on **Lifecycle Traceability** shows its whole life on one timeline.
- In the demo, **100 birds were received, then split into two flocks of 60 and 40**.
- Parent and child flocks are **linked automatically** from the stock movements.
- Feeding, treatment, weighing, deaths and sales all appear on the same timeline.
- **Why it matters:** audits, disease tracing, and buyers who ask where the animals came from.

## 6. Vet care that updates the animal's value (3:55 – 4:45)

- Individual animals have their own serial number. This diagnosis is for cow **COW00001**.
- The treatment plan used **10 doses of vaccine**. On submit, the app **issues the medicine from the store** for you.
- **To Capitalize** is ticked, so the app also creates a capitalisation entry.
- The cow's book value goes from **KES 10,000 to KES 11,000**.
- Finish on the **general ledger**: the entry was posted automatically.
- Also worth mentioning: diagnoses record symptoms, treatment plans and **withdrawal periods**.

## 7. For finance: costs become part of the animal's value (4:45 – 5:35)

- Under **IAS 41**, livestock is a **biological asset**.
- The flow is **feed issued** or **vet treatment**, then a **capitalisation entry** (a standard ERPNext Repack), then a **higher book value**.
- In the demo the ledger entry was:
  - **Dr** Stock In Hand: 1,000
  - **Cr** Cost of Goods Sold: 1,000
- Nobody posted a manual journal.
- **Controls:**
  - Costs are capitalised only while the batch's **capitalisation period is active**.
  - Cancelling a diagnosis **cancels the entries it created**.
  - Purchase-invoice costs (for example a vet's bill) can be allocated to a diagnosis.

## 8. Know how every flock is performing (5:35 – 6:35)

- **Dashboard:** daily population, mortality trend, survival %, feed used, and feed conversion ratio (FCR).
- **Performance profile:** the targets for each **day of age**, covering weight, daily feed, FCR and hen-day egg yield. Breed standard tables can be imported.
- **Batch Performance report:** actual vs. target for each flock.
- The demo flock:
  - started with **100 birds** and lost **5**
  - weighs **1.2 kg** against a **1.6 kg** target, so it is **25% underweight**
  - ate **40 kg** of feed against a **69 kg** target
- **Key message:** you see this in **days, not weeks**.

## 9. Early warnings, delivered as tasks (6:35 – 7:20)

- The app **checks the farm every day**, so nobody has to remember to open a report.
- **Four alert types:** mortality, below-target weight, overdue weighing, and overdue treatment follow-up.
- **You set the thresholds** with your farm manager. In the demo: daily mortality **≥ 2%** and at least **2 deaths**.
- A breach creates a **high-priority ToDo** for the responsible person, with a link to the flock.
- Each alert carries its evidence: **5 deaths out of 100 = 5%, against a 2% threshold**.
- Each alert has a condition state: **Active**, **Cleared** or **Unknown**. It doesn't create duplicate tasks.
- *Link back:* "This is the same underweight flock we just saw in the report."

## 10. What it means for you (7:20 – 8:05)

**For farmers and managers:**

- Record the day's work in minutes, on one screen.
- See every flock's age, history and performance.
- Get early warnings about deaths, low weight and missed checks.
- Plan vet care and breeding with full records.

**For finance:**

- Stock and costs flow straight from the farm, with no re-typing.
- Feed and vet costs are capitalised into livestock value (IAS 41).
- Every change in value is backed by a ledger entry.
- See profitability by batch.

**Close with:** one system, one set of numbers, for the people in the field and the people in the office.

## 11. Thank you / Questions (8:05 – 10:00)

- Recap in one breath: daily entry, traceability, vet care with capitalisation, performance vs. target, and early alerts.
- Offer to show any part again in more detail.

---

## Likely questions

- **"Do we need a separate system?"** No. It runs inside ERPNext and needs Frappe, ERPNext and HRMS.
- **"Who can see or change what?"** Standard ERPNext roles and permissions. Stock entries from Daily Farm Entry save as drafts for review.
- **"Does it handle individual animals or only flocks?"** Both: batches for flocks, serial numbers for individual animals such as dairy cows.
- **"Is this IAS 41 fair value?"** It builds each flock's or animal's **cost base** by capitalising feed and treatment costs into stock value. The app doesn't post fair-value remeasurements itself; your accountants handle those as usual.
- **"Can we use our breed's growth curves?"** Yes. Enter or import them as a performance profile, one row per day of age.
- **"What about eggs and milk?"** Produce collection receives them into a produce store as stock, separate from the flock. Hen-day egg yield is compared with targets for laying flocks.
- **"What about breeding?"** Breeding records, pregnancy checks, expected calving, offspring and pedigree.

## If something goes wrong

- **A video doesn't start:** click it to play. The same clips are in `Vuna_Livestock_Talk_clips/` and play in any video player.
- **Running over time:** shorten slide 3 to one sentence, and let the slide 5 video run with a single comment.
- **Time to spare:** mention breeding records and offspring, the Produce and Mortality reports, and batch profitability.
