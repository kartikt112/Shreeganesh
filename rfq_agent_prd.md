# RFQ Agent PRD (Development Department Automation)

## Objective

Build an AI agent that automates the **RFQ feasibility workflow of the
development department**.\
The agent will analyze customer drawings, generate ballooned drawings,
fill feasibility reports in the customer's format, and send them for
review.

This system is **Phase 1 of a larger AI Factory Operating System** where
all factory departments will eventually be connected and coordinated
through AI agents.

------------------------------------------------------------------------

# Current Manual Process (Development Department)

Email comes with:

• Engineering drawing (PDF / STEP)\
• RFQ details\
• Customer feasibility format (Excel)

Development team performs the following steps manually:

1.  Study the drawing
2.  Balloon all dimensions
3.  Extract specifications and notes
4.  Identify ID / OD / holes / threads etc
5.  Mark critical dimensions
6.  Check tolerance requirements
7.  Check machine availability
8.  Decide if manufacturing is feasible
9.  Identify deviations if required
10. Select measuring instruments
11. Prepare feasibility sheet
12. Send for costing

The RFQ agent must replicate this entire process.

------------------------------------------------------------------------

# System Overview

The RFQ agent will automate the process from **RFQ receipt → feasibility
report → costing preparation**.

Workflow:

Email RFQ\
↓\
AI parses drawing\
↓\
AI balloons dimensions\
↓\
AI extracts specifications\
↓\
AI checks machine capability\
↓\
AI checks measuring instruments\
↓\
AI fills feasibility sheet\
↓\
AI flags deviations\
↓\
AI sends report to development head for review

------------------------------------------------------------------------

# Step 1 --- RFQ Intake

The system monitors RFQ sources:

• Email inbox\
• Upload portal\
• Manual upload

The system extracts:

• Drawing files\
• Feasibility format\
• RFQ message\
• Quantity\
• Material (if mentioned)

RFQ record created:

RFQ ID\
Customer Name\
Part Name\
Drawing File\
Feasibility Template\
Quantity\
Material\
Received Date

------------------------------------------------------------------------

# Step 2 --- Drawing Parsing

The AI analyzes the engineering drawing.

Extract:

• Dimensions\
• Tolerances\
• Surface finish\
• GD&T symbols\
• Notes\
• Material\
• Part features

Output:

ID features\
OD features\
Hole features\
Threads\
Slots\
Chamfers\
Surface finish

------------------------------------------------------------------------

# Step 3 --- Ballooning

Every dimension in the drawing must be numbered.

Output:

Ballooned drawing (PDF)

Example:

Balloon 1 → OD diameter\
Balloon 2 → Length\
Balloon 3 → Hole position\
Balloon 4 → Thread pitch

Balloon numbers correspond to rows in the feasibility report.

------------------------------------------------------------------------

# Step 4 --- Feature Classification

AI determines what type of features exist.

Example:

OD Turning\
ID Boring\
Drilling\
Threading\
Milling\
Tapping\
Cutting\
Grooving

This determines the manufacturing process.

------------------------------------------------------------------------

# Step 5 --- Description Column

The system automatically fills the **Description column**.

Example:

ID Diameter\
OD Diameter\
Hole Diameter\
Thread M10\
Slot Width

------------------------------------------------------------------------

# Step 6 --- Specification Column

This includes:

• Dimension values\
• Tolerances\
• Notes

Example:

25 ±0.01\
M10 x 1.5\
Ra 0.8\
Position 0.02

------------------------------------------------------------------------

# Step 7 --- Criticality Identification

AI checks tolerances and GD&T.

Criticality rules example:

Tolerance \< 0.01 → Critical\
Surface finish \< 1.6 → Critical\
GD&T present → Critical

Column filled:

Criticality\
Yes / No

------------------------------------------------------------------------

# Step 8 --- Machine Selection

Based on operations AI selects machine.

Machine types:

CNC Lathe\
VMC\
Drilling\
Tapping\
Traub\
CNC Cutting

Machine assignment logic:

OD turning → CNC Lathe\
Slots → VMC\
Small precision parts → Traub\
Cutting operations → CNC cutting

------------------------------------------------------------------------

# Step 9 --- Machine Availability

System checks if machine exists in factory.

Database required:

Machine list with:

Machine name\
Operations supported\
Max part size\
Achievable tolerance

Output:

Machine available → Yes\
Machine available → No

If machine unavailable:

Outsource required

------------------------------------------------------------------------

# Step 10 --- Tolerance Column

System extracts tolerance range from drawing.

Example:

+0.01 / -0.02\
±0.005\
±0.02

Tolerance stored for capability check.

------------------------------------------------------------------------

# Step 11 --- Feasibility Decision

AI determines if dimension is feasible.

Rules:

Required tolerance ≤ machine capability → Feasible\
Required tolerance \> machine capability → Not feasible

Output column:

Feasible\
Yes / No

------------------------------------------------------------------------

# Step 12 --- Deviation Suggestion

If dimension cannot be achieved:

AI suggests deviation.

Example:

Required tolerance: ±0.005\
Machine capability: ±0.01

Deviation suggestion:\
Change tolerance to ±0.01

Deviation column must include:

• minimum variance\
• maximum variance

------------------------------------------------------------------------

# Step 13 --- Measuring Instrument Selection

Each dimension requires a measuring method.

Example:

Vernier caliper\
Micrometer\
Bore gauge\
Height gauge\
Thread gauge\
CMM\
Plug gauge\
Ring gauge

Rules:

Critical dimension → Gauge\
High precision → CMM\
Normal dimension → Vernier

If instrument unavailable:

Inspection outsourced

------------------------------------------------------------------------

# Step 14 --- Gauge Requirement

For each critical dimension:

Gauge required → Yes\
Gauge type → Plug / Ring / Thread

------------------------------------------------------------------------

# Step 15 --- Turnaround Time

System tracks feasibility completion time.

Fields:

RFQ received\
Feasibility started\
Feasibility completed

------------------------------------------------------------------------

# Step 16 --- Feasibility Report Generation

Customer feasibility format may differ.

System must:

• detect columns\
• map data automatically\
• preserve formatting

Output:

Completed feasibility Excel.

------------------------------------------------------------------------

# Step 17 --- Costing Preparation

Feasibility data is sent to costing.

Inputs for costing:

Raw material\
Operations\
Machine assignments\
Cycle time\
Outsourcing steps

Costing team will use this information.

------------------------------------------------------------------------

# Data Required for System

## Feasibility Report Formats

Different customers use different formats.

## Machine List

Machine name\
Operations\
Tolerance capability\
Max travel

## Operations List

Turning\
Drilling\
Tapping\
Milling\
Grinding\
Cutting

## Supplier List

Supplier name\
Material supplied\
Lead time

## Measuring Instrument List

Instrument name\
Accuracy\
Availability

------------------------------------------------------------------------

# APQP Time Plan Chart

Eventually displayed as dashboard showing:

RFQ received\
Feasibility completed\
Development review\
Costing completed\
Quote sent

------------------------------------------------------------------------

# Dashboard Requirements

RFQ tracking dashboard showing:

New RFQ\
Drawing parsed\
Ballooning complete\
Feasibility generated\
Awaiting review\
Sent to costing\
Quote sent

Development head should be able to:

• approve\
• edit\
• request revision

------------------------------------------------------------------------

# Future Integration Scope

Future agents:

Process Planning Agent\
Production Planning Agent\
Procurement Agent\
Quality Agent\
Inventory Agent\
Dispatch Agent

Future flow:

RFQ\
↓\
Process planning\
↓\
Production scheduling\
↓\
Material procurement\
↓\
Quality inspection\
↓\
Dispatch

------------------------------------------------------------------------

# Owner AI (Future Capability)

Factory owner should be able to ask:

Which RFQs are pending?\
Which RFQ has highest margin?\
Which machine will produce this part?\
Which supplier provides this material?
