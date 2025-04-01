# Legal Document Chatbot Color Code Reference

This document outlines the color codes used in the Legal Document Chatbot to highlight different categories of legal clauses.

## Color Codes

- **General Case Details**
  - **Color:** Gray
  - **Hex Code:** `#9E9E9E`
  - **Usage:** Used for general information and case background.

- **Penalty / Warnings**
  - **Color:** Red
  - **Hex Code:** `#F44336`
  - **Usage:** Highlights clauses that involve penalties or severe legal consequences.

- **Disputes / Legal Proceedings**
  - **Color:** Amber (Yellow)
  - **Hex Code:** `#FFC107`
  - **Usage:** Applied to clauses related to disputes, legal steps, or procedural instructions.

- **Court / Tribunal Orders (Decisions, Directions)**
  - **Color:** Blue
  - **Hex Code:** `#2196F3`
  - **Usage:** Highlights legal decisions, judgments, and official orders.

- **Positive Resolutions (Refunds, Withdrawals)**
  - **Color:** Green
  - **Hex Code:** `#4CAF50`
  - **Usage:** Used for clauses that describe resolutions, refunds, and withdrawals.

## How It Works

- When a PDF is uploaded, the system extracts the text and sends it to the assistant along with the above instructions.
- The assistant then generates a concise summary where important phrases are wrapped in `<span>` tags with the corresponding inline CSS for the color.
- For example, a penalty-related statement might be formatted as:  
  `<span style="color: #F44336;">This clause imposes a 10% penalty on late payments.</span>`

## Example

A sample output might look like:

```html
<p>The document indicates that <span style="color: #4CAF50;">standard financial clauses</span> are applied, while <span style="color: #F44336;">penalty clauses</span> indicate severe repercussions for non-compliance.</p>
