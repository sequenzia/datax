# Execution Plan

Tasks to execute: 50
Retry limit: 3 per task
Max parallel: 5 per wave

## WAVE 1 (2 tasks)
1. [#1] Set up Python backend project with FastAPI (unblocks 5)
2. [#2] Set up React frontend project with Vite (unblocks 2)

## WAVE 2 (6 tasks → 2 sub-waves)
### Sub-wave 2a (5 tasks)
3. [#8] Implement DuckDB file registration and schema detection (unblocks 5) — after [#1]
4. [#11] Build frontend IDE-style layout shell with sidebar (unblocks 5) — after [#2]
5. [#6] Implement Fernet encryption utilities for secrets (unblocks 2) — after [#1]
6. [#4] Create SQLAlchemy models for all entities (unblocks 1) — after [#1]
7. [#50] Implement health and readiness probe endpoints (unblocks 0) — after [#1]
### Sub-wave 2b (1 task)
8. [#3] Create Docker Compose development environment (unblocks 0) — after [#1, #2]

## WAVE 3 (6 tasks → 2 sub-waves)
### Sub-wave 3a (5 tasks)
9. [#5] Set up Alembic and create initial database migration (unblocks 6) — after [#4]
10. [#12] Implement frontend routing and page structure (unblocks 5) — after [#11]
11. [#24] Build results panel with stacked card layout (unblocks 1) — after [#11]
12. [#10] Implement data preview API endpoint with pagination (unblocks 0) — after [#8]
13. [#13] Build dark/light theme system (unblocks 0) — after [#11]
### Sub-wave 3b (1 task)
14. [#49] Implement responsive layout breakpoints (unblocks 0) — after [#11]

## WAVE 4 (10 tasks → 2 sub-waves)
### Sub-wave 4a (5 tasks)
15. [#27] Implement connection CRUD API endpoints (unblocks 5) — after [#5, #6]
16. [#21] Implement conversation CRUD API endpoints (unblocks 3) — after [#5]
17. [#14] Implement AI provider settings API endpoints (unblocks 2) — after [#5, #6]
18. [#41] Build SQL editor with CodeMirror or Monaco (unblocks 2) — after [#12]
19. [#45] Build dashboard overview page (unblocks 2) — after [#12]
### Sub-wave 4b (5 tasks)
20. [#43] Implement query execution, history, and saved queries API (unblocks 1) — after [#5, #8]
21. [#25] Build result card component with data table and explanation (unblocks 1) — after [#24]
22. [#9] Implement dataset CRUD API endpoints (unblocks 1) — after [#5]
23. [#7] Implement file upload endpoint with chunked upload (unblocks 0) — after [#5]
24. [#48] Build onboarding wizard component (unblocks 0) — after [#12]

## WAVE 5 (8 tasks → 2 sub-waves)
### Sub-wave 5a (5 tasks)
25. [#29] Implement schema introspection via SQLAlchemy (unblocks 3) — after [#27]
26. [#34] Build connection management UI (unblocks 2) — after [#12, #27]
27. [#16] Set up Pydantic AI agent with multi-provider support (unblocks 1) — after [#14]
28. [#28] Implement database connection testing endpoint (unblocks 1) — after [#27]
29. [#15] Build settings UI page (unblocks 0) — after [#12, #14]
### Sub-wave 5b (3 tasks)
30. [#44] Integrate SQL editor with query execution and results (unblocks 0) — after [#41, #43]
31. [#46] Build dataset and connection management views (unblocks 0) — after [#45, #9, #27]
32. [#47] Build conversation history browser (unblocks 0) — after [#45, #21]

## WAVE 6 (5 tasks)
33. [#33] Build unified schema registry API (unblocks 2) — after [#29, #8]
34. [#31] Implement live query proxy with read-only enforcement (unblocks 1) — after [#27, #29]
35. [#17] Implement schema context injection for AI agent (unblocks 1) — after [#16, #8]
36. [#35] Build connection form with test functionality (unblocks 0) — after [#34, #28]
37. [#30] Implement schema refresh endpoint (unblocks 0) — after [#29]

## WAVE 7 (4 tasks)
38. [#18] Implement natural language to SQL query generation (unblocks 3) — after [#17]
39. [#36] Build schema browser UI component (unblocks 0) — after [#34, #33]
40. [#42] Implement SQL editor autocomplete from schema registry (unblocks 0) — after [#41, #33]
41. [#32] Implement cross-source query orchestration (unblocks 0) — after [#31, #8]

## WAVE 8 (3 tasks)
42. [#20] Implement SSE streaming endpoint for conversation messages (unblocks 1) — after [#18, #21]
43. [#37] Implement AI chart type selection heuristics (unblocks 1) — after [#18]
44. [#19] Implement agentic self-correcting retry loop (unblocks 0) — after [#18]

## WAVE 9 (2 tasks)
45. [#22] Build chat panel UI component with streaming (unblocks 2) — after [#11, #20]
46. [#38] Implement Plotly chart configuration generation (unblocks 1) — after [#37]

## WAVE 10 (3 tasks)
47. [#39] Build interactive chart component with react-plotly.js (unblocks 1) — after [#38, #25]
48. [#23] Integrate streaming markdown rendering (unblocks 0) — after [#22]
49. [#26] Implement conversation persistence and history UI (unblocks 0) — after [#21, #22]

## WAVE 11 (1 task)
50. [#40] Implement chart export functionality (unblocks 0) — after [#39]
