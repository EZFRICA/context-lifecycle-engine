## b. Where it is produced from, and the leak this creates

The facet is generated **from the openers of the episodes the replay attributed
to the agent's cluster**, which are **raw user text**. This is Clio's layer 1, and it is the only place in the CLE where
user text passes through a model to produce something that will be stored.

The prompt must therefore, explicitly and in its own words:

1. instruct that no private information be reproduced;
2. forbid proper nouns of every kind, people, companies, products, places;
3. forbid quoting; the output describes a *kind of task*, not an instance;
4. state that the summary will be read by someone who has no access to the
   source, so anything that only makes sense with the source is wrong.

**This is the weakest link in the design, and it should be named as such.** A
prompt instruction is not a guard. §d exists because the
instruction alone cannot be trusted; the measurement of what leaks anyway is
part of the deliverable, not a follow-up.
