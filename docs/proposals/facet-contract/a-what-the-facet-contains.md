## a. What the facet contains

| property | value | why this value |
|---|---|---|
| length | **40–300 characters**, hard bounds | Long enough to distinguish two agents in one domain; short enough that an embedding is dominated by the task, not by prose style. Both bounds are validated, not advisory. |
| language | **English**, always, **now measured, no longer a hypothesis** |
| form | one sentence, verb-first, describing **what the agent does** | Not what the user is, not what the domain is. "Drafts weekly project recaps for a team", not "Project management". |
| forbidden | proper nouns, personal names, organisation names, URLs, file paths, numbers longer than 2 digits, any verbatim span of ≥ 6 words from the source | Each is a leak channel, and each is mechanically checkable, see §d. |
