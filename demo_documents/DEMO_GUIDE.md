# Caseload AI Demo Guide

These files are fictional test data created for a product demonstration. Do not present the names, dates, providers, or events as real client information.

## Files And Entities

| Upload file | Entity to enter | What it demonstrates |
| --- | --- | --- |
| `maya_chen_support_plan.txt` | Maya Chen | Goals, support strategies, risks, and review dates |
| `maya_chen_progress_report.txt` | Maya Chen | Progress across multiple goals, participant voice, and follow-up actions |
| `liam_oconnell_service_plan.txt` | Liam O'Connell | Service arrangements, consent, health safeguards, and employment goals |
| `liam_oconnell_shift_incident.txt` | Liam O'Connell | Incident details, participant voice, responsibility, and an open follow-up |

## Upload Setup

1. Open the app and use **Add or manage files**.
2. Enter `Maya Chen` in **Who is this for?** and upload the two Maya files. Clear the field afterwards.
3. Enter `Liam O'Connell` in **Who is this for?** and upload the two Liam files.
4. Wait for each file to appear in the document list before starting the chat demo.
5. If the app asks you to confirm an entity, select the matching existing entity rather than creating a duplicate.

Entering the entity name explicitly makes the demo predictable and shows entity-aware document grouping. The files also contain enough names for auto-detection if you want to demonstrate that flow separately.

## Suggested Demo Video Flow

### 1. Introduce the workspace

Show the dashboard and briefly explain that the workspace brings participant documents, searchable records, and operational follow-up into one place. Mention that the sample data is fictional.

### 2. Add Maya's documents

Open the upload area, enter `Maya Chen`, and upload both Maya files. Point out the document count and the entity label after ingestion. Do not upload all four files at once if you want the entity tagging step to be visible.

### 3. Add Liam's documents

Replace the participant name with `Liam O'Connell` and upload both Liam files. Show that the sidebar now contains two separate participant groups and that the incident file is searchable alongside the service plan.

### 4. Ask a cross-document question

Open **Ask Caseload AI** and ask one Maya question from the list below. Show the answer, then open **Show citations** to demonstrate the source file and supporting excerpt.

### 5. Compare participant context

Ask one Liam question. Explain that the answer is grounded in the uploaded documents and that changing the participant in the question changes the evidence being retrieved.

### 6. Show an action-oriented result

Ask about Liam's incident follow-up and the person responsible. This demonstrates that the system can surface dates, risks, participant voice, and next steps rather than only returning a generic summary.

### 7. Close the demo

Return to the dashboard or document list, point out the searchable document count, and explain that audio notes can be added in the same workflow. The audio recording and narration can be added separately.

## Questions To Ask On Camera

Use the questions exactly as written for a reliable demo. Wait for each response and open the citations panel when available.

### Maya Chen

- What goals is Maya Chen working on in her current support plan?
- How has Maya progressed with bus travel and meal preparation?
- What prompts did Maya need during the most recent bus practice?
- What did Maya say about her priorities for the next review?
- What support strategies should staff use when Maya becomes overwhelmed?
- What follow-up actions are due for Maya, and who owns them?

### Liam O'Connell

- What are Liam O'Connell's NDIS goals and weekly support arrangements?
- What happened during Liam's bicycle shed shift on 28 August 2026?
- What follow-up actions are open after Liam's fall, and who is responsible?
- What health and safety information should staff remember for Liam?
- What has Liam consented to share with the Bicycle Shed supervisor?
- When is Liam's first six-week progress review?

### Comparison Questions

- Compare Maya Chen's community participation goal with Liam O'Connell's employment goal.
- Which participant has an open safety follow-up, and what needs to happen next?
- What upcoming reviews or actions are mentioned across the uploaded files?

## Recording Tips

- Keep the browser zoom at 100% and show the full citation panel when demonstrating evidence.
- Use one participant name per question to make entity-aware retrieval easy to see.
- Give the answer time to load before asking the next question.
- If an answer is too broad, add the participant name and a date to the question.
- Avoid showing environment variables, API keys, database screens, or real client data in the recording.
