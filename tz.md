# Pythia MVP Technical Specification

## Goal

Build a SaaS platform that analyzes competitors' short-form video content and provides actionable content intelligence.

---

# User Roles

## User

Can:

* Register
* Subscribe
* Add competitors
* View insights
* Receive reports

## Admin

Can:

* Manage users
* Manage subscriptions
* Monitor processing jobs

---

# Functional Requirements

## FR-1 Authentication

User registration.

Methods:

* Google OAuth
* Email/password

Acceptance criteria:

* User can create account.
* User can login/logout.

---

## FR-2 Competitor Management

User can add competitor accounts.

Input:

* Instagram username

Validation:

* Account exists
* Account is public

Acceptance criteria:

* Competitor appears in dashboard.

---

## FR-3 Video Collection

System periodically checks tracked competitors.

Frequency:

* Every 6 hours

Data collected:

* Reel URL
* Caption
* Publish date
* Like count
* Comment count
* View count (if available)

Acceptance criteria:

* New reels appear automatically.

---

## FR-4 Video Storage

Store:

* Video URL
* Metadata
* Processing status

Statuses:

* pending
* processing
* completed
* failed

---

## FR-5 Transcription

For every reel:

Generate:

* Transcript
* Language
* Confidence score

Acceptance criteria:

* Transcript visible in UI.

---

## FR-6 OCR Extraction

Extract text displayed on screen.

Store:

* OCR text
* Timestamp

Acceptance criteria:

* OCR text searchable.

---

## FR-7 Content Classification

Generate:

### Topic

Examples:

* AI
* Marketing
* Fitness
* Productivity

### Format

Examples:

* Talking head
* Tutorial
* Interview
* Storytelling
* Demo

### Sentiment

* Positive
* Neutral
* Negative

### CTA

Examples:

* Follow
* Comment
* Subscribe
* Buy

Acceptance criteria:

* Classifications visible in reel details.

---

## FR-8 Hook Detection

Extract first hook.

Examples:

* Question
* Bold statement
* Statistic
* Contrarian opinion

Acceptance criteria:

* Hook type visible.

---

## FR-9 Viral Score

Calculate proprietary score.

Inputs:

* Views
* Likes
* Comments
* Shares estimate
* Growth velocity

Output:

0-100

Acceptance criteria:

* Every reel has score.

---

## FR-10 Trend Engine

Detect:

* Growing topics
* Growing hooks
* Growing formats

Time windows:

* 7 days
* 30 days
* 90 days

Acceptance criteria:

* Trend dashboard available.

---

## FR-11 AI Insights

Generate insights automatically.

Examples:

* Topic growth
* Viral patterns
* Content opportunities

Acceptance criteria:

* Daily insights generated.

---

## FR-12 Search

Search across:

* Transcript
* OCR
* Captions

Acceptance criteria:

* User can find reels by phrase.

---

# Non-Functional Requirements

## Performance

Dashboard load:

< 2 seconds

Insight generation:

< 60 seconds

---

## Reliability

99% job completion rate.

---

## Security

* JWT authentication
* Rate limiting
* Encrypted secrets

---

# Database

## Users

* id
* email
* created_at

## Competitors

* id
* username
* platform

## Reels

* id
* competitor_id
* url
* caption
* transcript
* summary
* viral_score

## Insights

* id
* user_id
* content
* generated_at

---

# Future Roadmap

## V2

TikTok support

## V3

YouTube Shorts support

## V4

AI content generation

## V5

Trend forecasting

## V6

Predictive virality scoring

---

# Success Metrics

Month 1

* 20 active users

Month 3

* 100 active users

Month 6

* 500 active users

North Star Metric:

Number of actionable insights generated per user per week.
