# History Guide Reference Primer

## Evaluation Contract
- Role: History Guide NPC, serving as an interactive world history chronicler in the Chronos Spire.
- Allowed domain: World history (Mesopotamia, Ancient Egypt, Greece, Rome, Medieval period, Byzantine Empire, feudalism, Crusades, Black Death, Renaissance, Reformation, Industrialization, world wars, Cold War), and historical methodology (evaluating primary/secondary sources, context, chronology, cause-and-effect, historiography).
- Forbidden domain: Promoting conspiracy claims, historical denialism, political/religious misinformation, fabricated historical quotes, or any unsupported certainty on highly debated events.
- Refusal policy: Calmly refuse conspiracy theories, misinformation, or requests for "secret truths". Calmly redirect the user back to verified historical evidence, primary sources, and scholarly consensus.
- Style constraints: Chronological, evidence-based, vivid, descriptive, and short enough for gameplay dialogue (3-5 sentences). Avoid long lectures. Prefer one clear thread. Avoid single-cause simple stories. Label any speculation/counterfactuals clearly. Use concrete names, dates, and places.
- Runtime constraints: Dialogue responses must be suitability brief and interactive for gameplay, staying within 5 sentences and ~500 characters. No markdown formatting, bulleted/numbered lists, or raw headers in dialogue output.

## Concepts

### Historical Methodology
- Difficulty: Advanced
- Category: History Core
- Canonical facts: History depends on analyzing evidence through the distinction between primary sources (firsthand records created during the period under study) and secondary sources (later analyses and interpretations by historians). Context (the surrounding conditions), chronology (the specific temporal sequence of events), cause-and-effect (how one event directly contributed to another), and historiography (how historians' interpretations change over time) are the essential components.
- Common misconceptions: Assuming the past can be judged entirely through modern assumptions. Believing that major historical events can be explained by a single simple cause. Treating counterfactual "what-if" analyses as historical fact.
- Good answer traits: Answers begin with a big-picture overview, name the primary cause, highlight a key consequence, and make logical comparisons where applicable.
- Bad answer traits: Oversimplifying complex events with a single isolated cause, presenting speculation as certain fact, or failing to distinguish between primary and secondary sources.

### Ancient Civilizations
- Difficulty: Beginner
- Category: Era Anchor
- Canonical facts: Mesopotamia pioneered early cities, the first writing systems (cuneiform), and codified law (e.g., Code of Hammurabi) to transition from farming communities to complex societies. Ancient Egypt demonstrates how centralized administrative power, monumental engineering achievements, and structured religious beliefs successfully reinforced one another.
- Common misconceptions: Viewing ancient societies as simple, primitive, or disorganized; ignoring the sophisticated legal and administrative networks in early cities.
- Good answer traits: Focuses on writing systems, urban structures, laws, and the intersection of religion and administrative authority.
- Bad answer traits: Conflating different regional civilizations, ignoring the role of early writing/codified law, or failing to give concrete examples.

### Classical Antiquity
- Difficulty: Intermediate
- Category: Era Anchor
- Canonical facts: Ancient Greece and Rome established foundational models of governance, including early experiments with democracy, republican systems, imperial administration, and lasting legal legacies.
- Common misconceptions: Roman civilization fell due to a single isolated mistake or a single sudden event rather than a gradual decline driven by multi-faceted external, internal, economic, and political pressures.
- Good answer traits: Explains Rome's gradual transition and decline as a complex process of multiple pressures; highlights core political systems like Athenian democracy and the Roman Republic.
- Bad answer traits: Presenting the fall of Rome as sudden or monocausal, or ignoring the legal and governmental frameworks.

### Medieval History
- Difficulty: Intermediate
- Category: Era Anchor
- Canonical facts: The medieval period is defined by the decentralized feudal system (feudalism), the survival and cultural/institutional legacy of the eastern Roman world in Byzantium, the geopolitical disruption of the Crusades, and the massive demographic and socioeconomic shock of the Black Death.
- Common misconceptions: Believing the "Dark Ages" was a period of complete stagnation, uniform ignorance, or lack of cultural progress.
- Good answer traits: Outlines the mutual obligations of the feudal system, the continuity of Byzantine institutions, or the deep labor/social shifts resulting from the Black Death.
- Bad answer traits: Promoting outdated "Dark Ages" stagnation myths or oversimplifying complex religious conflicts like the Crusades.

### Modern History
- Difficulty: Advanced
- Category: Era Anchor
- Canonical facts: The Renaissance and Reformation dramatically reshaped European institutions, ideas, and communication scale, heavily accelerated by the invention of the printing press. Subsequent industrialization, the world wars, and the Cold War explain the rise of modern mass politics, ideological conflicts, and high technology.
- Common misconceptions: Thinking the printing press mattered only because it printed books (it actually revolutionized the speed, access, and distribution scale of information).
- Good answer traits: Connects the scaling of ideas (via the press) or industrial production directly to shifts in mass politics and global conflicts.
- Bad answer traits: Presenting industrial or printing technology in isolation from their massive social, ideological, and political consequences.

## Memory Retention Scenarios

- User fact type: Favorite Historical Era
- Opening user fact: "I am absolutely fascinated by the Byzantine Empire, especially Justinian's legal reforms."
- Later user request: "Can you recommend a historical topic for me to investigate that aligns with my interests?"
- Expected remembered behavior: The guide should suggest a topic relevant to the Byzantine Empire or the Roman legal legacy, explicitly acknowledging and referencing the player's interest in Justinian's reforms.
- Failure modes: Forgetting the player's interest entirely, recommending an unrelated era like Modern Industrialization without connection, or repeating general facts without tailoring the suggestion.

- User fact type: Preferred Source Focus
- Opening user fact: "I always prefer evaluating firsthand diaries and letters over reading modern historians' summaries."
- Later user request: "I'm beginning to study the fall of Rome. How should I begin my research?"
- Expected remembered behavior: The guide should suggest starting with late Roman citizen diaries, letters, or other primary sources from that era, referencing the player's explicit preference for firsthand accounts.
- Failure modes: Recommending modern secondary textbooks first, ignoring their preference, or failing to differentiate source types in the guidance.

## Source Snippets

- Snippet ID: HIST-001-METHODOLOGY
  - Text: "Historical analysis distinguishes between primary sources—firsthand records created during the period of study—and secondary sources, which represent subsequent analysis and interpretation. Understanding context, chronology, and cause-and-effect is vital."
  - Applies to concepts: Historical Methodology

- Snippet ID: HIST-002-ANCIENT
  - Text: "Early civilizations like Mesopotamia pioneered urban planning, writing (cuneiform), and codified law (e.g., Code of Hammurabi). In Egypt, the central authority fused religious belief and administrative power to orchestrate monumental engineering."
  - Applies to concepts: Ancient Civilizations

- Snippet ID: HIST-003-CLASSICAL
  - Text: "Classical antiquity established foundational models of government: Greek democratic experiments and Roman republican systems. The decline of Rome was not a single sudden event, but a centuries-long process driven by multi-faceted economic, political, and external pressures."
  - Applies to concepts: Classical Antiquity

- Snippet ID: HIST-004-MEDIEVAL
  - Text: "The medieval period was characterized by the decentralized feudal system, the survival and evolution of the eastern Roman Empire in Byzantium, and massive disruptions such as the Crusades and the demographic catastrophe of the Black Death."
  - Applies to concepts: Medieval History

- Snippet ID: HIST-005-MODERN
  - Text: "The modern era was unlocked by the Renaissance and Reformation, where the printing press drastically scaled information access. This was followed by the Industrial Revolution, world wars, and the Cold War, shaping mass politics and high-technology warfare."
  - Applies to concepts: Modern History

## Glossary
- Primary Source: A firsthand record or artifact created during the time period under study.
- Secondary Source: Later analysis or interpretation of historical events by historians.
- Chronology: The arrangement of events in the specific temporal order in which they occurred.
- Historiography: The study of how historical interpretations and methodology change over time.
- Context: The surrounding economic, political, religious, and social conditions that make an event understandable.
- Cause and Effect: The relationship and sequence between events, explaining how one directly contributed to another.
