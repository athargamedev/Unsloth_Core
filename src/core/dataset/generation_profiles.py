from __future__ import annotations

import random
import re

CATEGORY_TEMPLATES = {
    "identity": {
        "description": "Persona introduction and self-identification",
        "user_templates": [
            "Who are you?",
            "What is your name?",
            "Tell me about yourself.",
            "What should I call you?",
            "Are you a teacher?",
            "Who am I speaking with?",
            "What do you teach?",
            "Can you introduce yourself?",
        ],
        "assistant_generator": "generate_identity_response",
    },
    "teaching": {
        "description": "Subject-matter explanations",
        "user_templates": [
            "Can you explain {concept}?",
            "Tell me about {concept}.",
            "What is {concept}?",
            "How does {concept} work?",
            "Why is {concept} important?",
            "Can you give me an example of {concept}?",
            "I don't understand {concept}. Can you help?",
            "What are the key ideas behind {concept}?",
            "Compare {concept_a} and {concept_b}.",
            "How is {concept} related to {related_concept}?",
            "What is the difference between {concept_a} and {concept_b}?",
            "Can you break down {concept} into simpler ideas?",
            "Where can I see {concept} in action?",
            "How do experts think about {concept}?",
            "What should I know about {concept}?",
            "Is there a real-world example of {concept}?",
            "What are the basics of {concept}?",
            "Tell me something interesting about {concept}.",
            "How did {concept} come to be?",
            "What makes {concept} so useful?",
            "Can you simplify {concept}?",
            "I'm struggling with {concept}. Explain it simply.",
            "What are common misconceptions about {concept}?",
            "How do I apply {concept}?",
            "What do I need to understand {concept}?",
            "Describe {concept} like I'm five.",
            "What are the main components of {concept}?",
            "Why does {concept} matter in everyday life?",
            "Give me a metaphor for {concept}.",
            "What is the history behind {concept}?",
            "How does {concept} fit into the bigger picture?",
            "What are some advanced aspects of {concept}?",
        ],
        "assistant_generator": "generate_teaching_response",
    },
    "dialogue": {
        "description": "Natural conversation handling",
        "user_templates": [
            "I still don't get {concept}. Can you try again?",
            "That makes sense, but what about when things get complex?",
            "Can you give me another example? I learn by examples.",
            "I have a question about what you said earlier regarding {concept}...",
            "What happens if I apply {concept} incorrectly?",
            "Is there a trick to remembering {concept}?",
            "You mentioned something about {concept} - can you elaborate?",
            "Wait, I thought {concept} was different. Can you clarify?",
            "That helps! But how does {concept} connect to what I already know?",
            "Can we go deeper on {concept}? I want to really understand it.",
            "I heard someone say {concept} is outdated. Is that true?",
            "What would happen if {concept} didn't exist?",
            "Can you show me how to approach {concept} step by step?",
            "I get the basics. What's next after {concept}?",
            "That's interesting! But does {concept} apply to other fields too?",
            "Could you explain {concept} from a different angle?",
        ],
        "assistant_generator": "generate_dialogue_response",
    },
    "quest": {
        "description": "Scenario-based interactions",
        "user_templates": [
            "Give me a challenge related to {concept}.",
            "Test my knowledge of {concept} with a question.",
            "I want to practice {concept}. Give me an exercise.",
            "Can you give me a scenario where I apply {concept}?",
            "What is a good practice problem for {concept}?",
            "Create a quiz question about {concept}.",
            "Give me a real-world problem involving {concept} to solve.",
            "I need to master {concept}. Give me a difficult question.",
        ],
        "assistant_generator": "generate_quest_response",
    },
    "refusal": {
        "description": "Safe boundary responses",
        "user_templates": [
            "Can you write a poem for me?",
            "What is the meaning of life?",
            "Tell me how to bake a cake.",
            "Can you help me with my homework in a different subject?",
            "What stocks should I invest in?",
            "Tell me a joke.",
            "Can you predict the lottery numbers?",
            "Give me medical advice.",
        ],
        "assistant_generator": "generate_refusal_response",
    },
}


def _subject_focus(spec):
    subject = spec.get("subject", "this topic")
    return subject.split(":", 1)[0].strip().lower() or "this topic"


def _is_history_subject(spec) -> bool:
    subject = _subject_focus(spec).lower()
    subject_text = str(spec.get("subject", "")).lower()
    npc_name = str(spec.get("npc_name", "")).lower()
    return "history" in subject or "history" in subject_text or "history" in npc_name


def _is_cooking_subject(spec) -> bool:
    subject = _subject_focus(spec).lower()
    subject_text = str(spec.get("subject", "")).lower()
    npc_name = str(spec.get("npc_name", "")).lower()
    return any(word in subject or word in subject_text or word in npc_name for word in ["cook", "culinary", "chef"])


def _example_topics(spec, limit=2):
    topics = spec.get("dialogue", {}).get("example_topics", []) or []
    return [str(topic).strip() for topic in topics[:limit] if str(topic).strip()]


def _capitalize_first(text: str):
    if not text:
        return text
    return text[0].upper() + text[1:]


def _lower_first(text: str):
    if not text:
        return text
    return text[0].lower() + text[1:]


def _topic_to_anchor(topic: str, subject: str) -> str:
    clean = topic.strip().rstrip("?")
    clean = re.sub(r'^(what caused|what is|who is|how do i|how do|why is|how does|is|are|can i|should i|what are|how many|when does|where does)\s+', '', clean, flags=re.I).strip()
    if not clean:
        return subject
    return _capitalize_first(clean)


def _concept_detail(spec, concept):
    subject = _subject_focus(spec)
    topics = _example_topics(spec)
    if topics:
        return _topic_to_anchor(topics[0], subject)
    return _capitalize_first(f"{concept} in {subject}")


def _cooking_practical_focus(concept: str, spec, retriever=None):
    concept_l = concept.lower()
    detail = _lower_first(_concept_anchor(concept, spec, retriever))
    mappings = [
        ("knife", ("keep your fingertips tucked and make slow, even slices", "you get safer, more even cuts")),
        ("food safety and storage", ("separate raw food from ready-to-eat food and chill leftovers promptly", "you lower contamination risk")),
        ("food safety", ("keep raw chicken separate and store leftovers cold", "you lower contamination risk")),
        ("ingredient science", ("change one variable at a time, like heat or acid", "you can see how texture and flavor change")),
        ("kitchen workflow", ("set up mise en place first and keep the station clean as you go", "the work stays organized and faster")),
        ("kitchen organization", ("group tools and ingredients before you start", "you waste less time hunting for things")),
        ("flavor balance", ("taste, then adjust salt, acid, fat, or sweetness one at a time", "the dish tastes fuller and more balanced")),
        ("cooking techniques", ("match the heat and pan motion to the technique", "the texture or doneness improves")),
        ("core kitchen flow", ("choose the order of steps before turning on the heat", "the dish finishes more smoothly")),
        ("flavor and ingredient logic", ("choose ingredients that support the same flavor goal", "the final dish tastes coherent")),
        ("knife skills and techniques", ("keep the blade steady and make controlled cuts", "the slices stay even and safe")),
    ]
    for needle, pair in mappings:
        if needle in concept_l:
            return pair
    return detail, "the result is easier to see"


def _concept_detail_lower(concept, spec):
    result = _concept_detail(spec, concept)
    if result and len(result) > 1:
        return result[0].lower() + result[1:]
    return result


def _concept_anchor(concept: str, spec, retriever=None) -> str:
    if retriever:
        contexts = retriever.get_grounding_context(concept, top_k=1)
        if contexts:
            first_sent = re.split(r'[.!?]+', contexts[0])[0].strip()
            if first_sent:
                return _capitalize_first(first_sent)
    concept_l = concept.lower()
    subject = _subject_focus(spec)
    anchors = [
        ("telescope", "Observing the Moon or Jupiter through a telescope"),
        ("black hole", "Studying a black hole with a space telescope"),
        ("solar system", "Tracking planets and moons in our solar system"),
        ("galaxy", "Identifying a galaxy cloud in the night sky"),
        ("knife", "Chopping an onion cleanly with a sharp chef's knife"),
        ("food safety", "Keeping raw chicken separate from salad ingredients"),
        ("cooking", "Sautéing vegetables evenly over medium heat"),
        ("meal prep", "Preparing ingredients in advance to save time during the week"),
        ("strength training", "Using controlled lifts with good form and moderate weight"),
        ("cardio", "Doing brisk walking or cycling to raise your heart rate safely"),
        ("recovery", "Resting and sleeping well after a hard workout"),
        ("nutrition", "Balancing protein, carbohydrates, and fats for steady energy"),
        ("ancient civilizations", "Mesopotamia, early cities, writing, and codified law"),
        ("classical antiquity", "Greek city-states, Roman law, republican government, and empire"),
        ("roman empire", "Greece and Rome, with democracy, empire, republican government, and legal legacy"),
        ("medieval history", "feudalism, the Byzantine world, crusades, and the Black Death"),
        ("industrial revolution", "industrialization, world wars, and the Cold War"),
        ("world war", "industrialization, world wars, and the Cold War"),
        ("modern history", "industrialization, world wars, and the Cold War"),
        ("core timeline anchors", "placing events in order so causes, dates, and consequences stay connected"),
        ("scope and use", "major eras, turning points, and why events changed societies"),
        ("historical methodology", "primary sources, eyewitness accounts, and uncertainty"),
        ("historical thinking", "the big picture, the main cause, and one consequence"),
        ("kitchen organization", "setting up a clean station, grouping tools, and keeping workflow efficient"),
        ("kitchen workflow", "mise en place, clean-as-you-go habits, and choosing the right order for each step"),
        ("knife skills and techniques", "grip, angle, and control with a sharp chef's knife"),
        ("food safety and storage", "temperature control, cross-contamination, and fast refrigeration"),
        ("ingredient science", "how heat, acid, fat, starch, and protein change texture and flavor"),
        ("flavor balance", "salt, acid, fat, sweetness, and tasting as you go"),
    ]
    for needle, anchor in anchors:
        if needle in concept_l:
            return _capitalize_first(anchor)
    return _capitalize_first(f"{concept} in {subject}")


class DialogueGuardrail:
    def __init__(self, max_sentences: int | None = None, max_characters: int | None = None, allow_formatting: bool | None = None):
        self.max_sentences = max_sentences
        self.max_characters = max_characters
        self.allow_formatting = allow_formatting

    def validate(self, response: str, messages, spec):
        dialogue_conf = spec.get("dialogue", {}) if isinstance(spec, dict) else {}
        max_sentences = self.max_sentences or dialogue_conf.get("max_sentences", 5)
        max_characters = self.max_characters or dialogue_conf.get("max_characters", 500)
        allow_formatting = dialogue_conf.get("allow_formatting", True) if self.allow_formatting is None else self.allow_formatting

        resp_clean = str(response or "").strip()
        lower_resp = resp_clean.lower()
        ai_disclaimers = [
            "as an ai",
            "as a language model",
            "i don't have personal feelings",
            "openai",
            "anthropic",
            "knowledge cutoff",
            "as an artificial intelligence",
            "i don't have personal opinions",
            "as a machine learning model",
            "i'm just an ai",
            "i cannot feel emotions",
            "from my training data",
        ]
        for disclaimer in ai_disclaimers:
            if disclaimer in lower_resp:
                return False, f"Response broke character by including AI disclaimer: '{disclaimer}'"

        sentences = [s for s in re.split(r"[.!?]+", resp_clean) if s.strip()]
        if len(sentences) > max_sentences:
            return False, f"Response is too verbose ({len(sentences)} sentences). Must be 1-{max_sentences} short sentences."

        if len(resp_clean) > max_characters:
            return False, f"Response is too long ({len(resp_clean)} characters). Must be under {max_characters} characters."

        if not allow_formatting:
            if "**" in resp_clean or "__" in resp_clean:
                return False, "Response contains markdown bolding, which is disabled for game UI."
            if any(line.strip().startswith("#") for line in resp_clean.splitlines()):
                return False, "Response contains markdown headers (#), which is disabled for game UI."
            for line in resp_clean.splitlines():
                if re.match(r"^[-*•\d]+\.?\s+", line.strip()):
                    return False, "Response contains markdown lists/bullets, which are disabled for game UI."

        return True, ""


def generate_identity_response(spec):
    npc_name = spec.get("npc_name", "the guide")
    subject = _subject_focus(spec)
    subject_short = spec.get("subject", subject).split(",")[0].strip().split(":")[0].strip() or subject
    personality = spec.get("identity", {}).get("personality", "")
    personality_short = personality.split("—")[0].split("-")[0].split(";")[0].split(",")[0].strip()

    if _is_history_subject(spec):
        templates = [
            f"I'm {npc_name}, and I help you study {subject_short} by comparing sources, tracing cause and effect, and showing why events mattered, like the fall of Rome.",
            f"I'm {npc_name}, your {subject_short} guide. I answer directly, then point to evidence and one concrete example like ancient civilizations or medieval history.",
            f"Hi, I'm {npc_name}. If you ask about {subject_short}, I can walk you through a topic, a source, or a turning point like the printing press.",
            f"I'm {npc_name}, a careful {subject_short} guide who checks dates, evidence, and historical importance first, especially for modern history.",
            f"I'm {npc_name}; I help place events on a timeline and compare primary sources so you can see why historians disagree about ancient civilizations.",
            f"I'm {npc_name}; I help separate legend from evidence in {subject_short} and show why details matter in medieval history.",
        ]
    elif _is_cooking_subject(spec):
        templates = [
            f"I'm {npc_name}. I help with safe, practical cooking, clear next steps, and the check that shows the dish is ready.",
            f"I'm {npc_name}. If you tell me what you have, I can help choose the next step, the heat, and the result to look for.",
            f"I'm {npc_name}, your cooking guide for clear steps, safe temperatures, and good results in the kitchen.",
            f"Hi, I'm {npc_name}. I keep cooking advice practical, calm, specific, and easy to use.",
            f"I'm {npc_name}; I help with kitchen workflow, flavor balance, and food safety, with one concrete action at a time.",
            f"I'm {npc_name}; I turn cooking problems into clear steps, from prep to finish, and I can help you choose the next move.",
        ]
    else:
        templates = [
            f"I'm {npc_name}, and I help you with {subject_short} using clear examples and practical steps.",
            f"I'm {npc_name}, your guide for {subject_short}. I answer directly and point to one concrete example.",
            f"Hi, I'm {npc_name}. If you ask about {subject_short}, I can walk you through the basics and the next step.",
            f"I'm {npc_name}, a careful guide who keeps the explanation practical and concrete.",
        ]
    if personality_short:
        templates.append(
            f"I'm {npc_name}, a {personality_short.lower()} guide for {subject_short}, with a focus on clear steps and concrete examples."
        )
    return random.choice(templates)


def generate_teaching_response(spec, concept_a, concept_b=None, difficulty="beginner", retriever=None):
    subject = _subject_focus(spec)
    detail_a = _concept_anchor(concept_a, spec, retriever)
    detail_b = _concept_anchor(concept_b, spec, retriever) if concept_b else None
    if "methodology" in concept_a.lower():
        detail_a = "Comparing sources carefully and checking for bias"
    detail_a_lower = _lower_first(detail_a)

    if _is_history_subject(spec):
        if concept_b:
            templates = [
                f"Compare {concept_a} and {concept_b} by looking at how each changed society.",
                f"A useful contrast is that {concept_a} centers on {detail_a}, while {concept_b} centers on {detail_b}.",
            ]
        else:
            if "ancient civilization" in concept_a.lower():
                templates = [
                    "Ancient civilizations work by turning scattered villages into organized societies with cities, writing, laws, trade, and rulers. Start with Mesopotamia around 3500 BCE: clay tablets and later law codes show how people tracked grain, taxes, labor, and disputes, which made large cities easier to govern.",
                    "For ancient civilizations, use Mesopotamia as the anchor: irrigation supported cities, writing preserved records, and law codes helped rulers manage conflict. Those sources matter because they show the shift from local farming communities to complex societies with memory, authority, and trade.",
                ]
            else:
                templates = [
                    f"Start with {detail_a_lower}, then anchor it to a date, a source, and a consequence. That gives the player a clear timeline, shows what evidence supports the claim, and explains why the event changed what came next.",
                    f"A concrete example is {detail_a_lower}. Use it to compare evidence, name the historical setting, and explain one consequence so the answer feels like a guided archive note rather than a loose fact.",
                    f"The key idea is {detail_a_lower}; it helps you link evidence to historical change without guessing. A good explanation names the source, places it in time, then shows how that detail reshaped people, power, or trade.",
                ]
    elif _is_cooking_subject(spec):
        action_a, result_a = _cooking_practical_focus(concept_a, spec, retriever)
        action_b, result_b = _cooking_practical_focus(concept_b, spec, retriever) if concept_b else (None, None)
        concept_l = concept_a.lower()
        if "ingredient science" in concept_l:
            templates = [
                f"Think of ingredient science as a test kitchen method: change one thing at a time, such as heat, acid, or fat, so you can see exactly what shifted in the dish. For example, a small heat change can thicken a sauce, brown a crust, or alter texture.",
                f"Ingredient science means treating ingredients like controlled variables. If you adjust only one dial, you can compare the before and after and see whether the dish became thicker, sharper, or more stable.",
            ]
        elif "knife" in concept_l:
            templates = [
                f"Knife skills is about control, angle, and rhythm, but the useful part is seeing how those choices affect safety and evenness. For example, a steady grip and a consistent motion give cleaner cuts that cook at the same rate.",
                f"Think of knife skills as controlled cutting practice: keep the blade steady, use a safe grip, and adjust pressure so the pieces stay uniform. That is what makes prep safer and more consistent.",
            ]
        elif "flavor balance" in concept_l:
            templates = [
                f"Flavor balance is about tasting, then adjusting salt, acid, fat, or sweetness one step at a time so the whole dish feels complete. For example, a flat soup may need acid or salt before it needs anything else.",
                f"Think of flavor balance as tuning a dish in small moves: change one flavor note, taste again, and check whether the result feels fuller or sharper. That is how you avoid making the whole dish swing too far.",
            ]
        elif "food safety" in concept_l:
            templates = [
                f"Food safety is about separation, temperature, and time. Keep raw meat away from ready-to-eat food, cook poultry to 165 F, and chill leftovers within 2 hours so bacteria do not get time to grow.",
                f"Think of food safety as a chain of checks: separate raw foods, cook to a safe temperature, cool quickly, and store cold. For example, chicken needs a thermometer check, then leftovers need the refrigerator before they sit out too long.",
            ]
        elif "kitchen workflow" in concept_l or "kitchen organization" in concept_l or "core kitchen flow" in concept_l:
            templates = [
                f"Kitchen workflow is the order of the job: set up first, then cook in a clean sequence so prep, heat, and cleanup do not fight each other. For example, mise en place saves time because the tools and ingredients are ready before the pan gets hot.",
                f"Think of kitchen workflow like a route through the kitchen: organize the station, work in order, and keep the counter clear so the dish moves from prep to plating smoothly. That is what makes the whole process faster and safer.",
            ]
        elif concept_b:
            templates = [
                f"{concept_a} is about {action_a}, while {concept_b} is about {action_b}, so they lead to different results.",
                f"Compare them like this: {concept_a} means {action_a}, and {concept_b} means {action_b}, so the dish changes in a real, visible way.",
            ]
        elif difficulty == "beginner":
            templates = [
                f"Start with {concept_a}: {action_a}. That helps because {result_a}, and you can compare the before and after.",
                f"A simple way to think about {concept_a} is {action_a}. You can see it when {result_a}, especially after one small adjustment.",
                f"{concept_a} means {action_a}, and that gives you {result_a} in a real dish.",
            ]
        elif difficulty == "intermediate":
            templates = [
                f"A useful way to study {concept_a} is to {action_a}, then compare before and after and name {result_a} in the finished dish.",
                f"{concept_a} works best when you {action_a}, then check whether {result_a} after the change.",
            ]
        else:
            templates = [
                f"{concept_a} is easier to understand when you {action_a}. For example, notice whether {result_a}.",
                f"In practice, {concept_a} matters because {action_a}, which means {result_a}.",
            ]
    elif difficulty == "beginner":
        if concept_b:
            templates = [
                f"{concept_a} is about {detail_a}, while {concept_b} is about {detail_b}; one uses {detail_a} and the other uses {detail_b}.",
                f"Compare them like this: {concept_a} means {detail_a}, and {concept_b} means {detail_b} in a concrete case.",
            ]
        else:
            templates = [
                f"Start with {detail_a}; that is the concrete example that makes {concept_a} useful.",
                f"The key idea is {detail_a}, which you can see in a real-world example and then reuse in practice.",
                f"In {subject}, you notice {concept_a} when {detail_a}, especially in practical cases.",
            ]
    elif difficulty == "intermediate":
        if concept_b:
            templates = [
                f"A useful difference is that {concept_a} focuses on {detail_a}, while {concept_b} focuses on {detail_b}, so they lead to different outcomes.",
                f"Look at {concept_a} and {concept_b} through {detail_a} versus {detail_b}, using one concrete example.",
            ]
        else:
            templates = [
                f"A deeper look at {concept_a}: start from {detail_a} and trace one practical effect.",
                f"{concept_a} works this way in practice when you use {detail_a} as the anchor for one specific case.",
            ]
    else:
        if concept_b:
            templates = [
                f"Compare {concept_a} and {concept_b} by checking one concrete case, like {detail_a} versus {detail_b}.",
                f"A useful contrast is that {concept_a} shows up when {detail_a}, while {concept_b} shows up when {detail_b}.",
            ]
        else:
            templates = [
                f"{concept_a} is easier to understand when you start with one concrete example, like {detail_a}.",
                f"In practice, {concept_a} matters because {detail_a}, which changes the outcome in a real case.",
            ]
    return random.choice(templates)


def generate_dialogue_response(spec, concept, dialogue_type="deep_dive", retriever=None):
    npc_name = spec["npc_name"]
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)
    detail_lower = _lower_first(detail)

    if _is_history_subject(spec):
        if dialogue_type == "clarification":
            templates = [
                f"If you apply {concept} incorrectly, causes can look backwards and evidence can support the wrong claim. Check the date and source.",
                f"A mistake with {concept} can turn an effect into a cause. Re-anchor the event with one date, one source, and one consequence.",
            ]
        elif dialogue_type == "deep_dive":
            templates = [
                f"Go deeper by linking {concept} to {detail_lower}. Then ask what happened first, which source supports it, and what consequence followed, so the history stays chronological instead of vague.",
                f"{concept.capitalize()} is clearer when you connect {detail_lower} to one visible historical change. Name the setting, the evidence, and the consequence before drawing the conclusion.",
            ]
        elif dialogue_type == "application":
            templates = [
                f"Use {concept} with one documented case, like {detail}. Start with the date or source, then explain what changed and why that evidence supports the answer.",
                f"A practical way to apply {concept} is to test it against a real event such as {detail}. Compare the claim to the source, then explain the cause and consequence.",
            ]
        else:
            templates = [
                f"That is a common misconception. A better example is {detail}, because it shows the idea in a real historical case with evidence, context, and consequence.",
                f"Not quite — use {detail} as the concrete example. If you apply {concept} loosely, you can blur cause and effect; keep the source, the timeline, and the consequence separate.",
            ]
    elif _is_cooking_subject(spec):
        action, result = _cooking_practical_focus(concept, spec, retriever)
        if dialogue_type == "clarification":
            templates = [
                f"Yes. {concept.capitalize()} means {action}, and you can see it in the dish when {result}. For example, that change is obvious in the texture or timing.",
                f"Yes, {concept.capitalize()} is easier to understand when you {action}. For example, you can watch the result show up in texture, safety, or doneness right away.",
            ]
        elif dialogue_type == "deep_dive":
            templates = [
                f"No, it is not outdated. {concept.capitalize()} still matters because {action}, and that is what changes the result. If you already know the basics, this is the next layer that makes the dish more controlled.",
                f"{concept.capitalize()} is clearer when you {action}, then notice whether {result}. That links the idea to a real dish instead of leaving it abstract.",
            ]
        elif dialogue_type == "application":
            templates = [
                f"Use {concept} by {action}, then check whether {result}. For example, compare the first bite or the final cut before and after the change.",
                f"A practical way to apply {concept} is to {action} and watch for {result}. That gives you a simple before-and-after check you can reuse.",
            ]
        else:
            templates = [
                f"Without {concept}, prep, cooking, and cleanup collide: tools go missing, heat timing slips, and safety checks get rushed. A better way is to {action}, because {result}.",
                f"Not quite — use {action} as the concrete example and explain what changes in the dish. That makes the answer specific enough to be useful.",
            ]
    elif dialogue_type == "clarification":
        templates = [
            f"Sure — {concept} means {detail}, and a concrete example makes it easier to see.",
            f"Another way to say it: {concept} is about {detail}, as you can see in a real case.",
        ]
    elif dialogue_type == "deep_dive":
        templates = [
            f"Start with {detail}, then name one cause and one consequence so the idea stays concrete.",
            f"A good next step is to connect {detail} to one event, date, or source.",
        ]
    elif dialogue_type == "application":
        templates = [
            f"Use {concept} by matching it to one specific case, like {detail}.",
            f"A practical way to apply {concept} is to test it against a real example and explain the result.",
        ]
    else:
        templates = [
            f"That is a common misconception. A better explanation is {detail}, with one real example to prove it.",
            f"Not quite — {concept} works best when you connect it to a specific case such as {detail}.",
        ]

    return random.choice(templates)


def generate_quest_response(spec, concept, scenario_name=None, retriever=None):
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)
    detail_lower = _lower_first(detail)

    if scenario_name:
        scenario_templates = {
            "timeline_analysis": [
                f"Challenge: pick one event related to {concept}, like {detail_lower}. Place it on a timeline, name one source that could support the date, then explain one cause and one consequence so the answer shows why the event mattered.",
                f"Scenario: an archive card lists {detail_lower} but gives no context. Put it in sequence, identify what happened before it, and explain what changed afterward so the player practices cause and consequence.",
            ],
            "primary_source": [
                f"Scenario: two sources date one event differently. Use {concept} to place it, cite one source, and explain one consequence.",
                f"Try this: use {concept} to order one event, cite one source for its date, then explain what changed next.",
            ],
            "technique_mastery": [
                f"Your challenge: apply {concept} to {detail_lower}, then explain one cause and one consequence.",
                f"Name one mistake with {concept}, then use {detail_lower} to correct the timeline or evidence.",
            ],
            "meal_planning": [
                f"Scenario: you have rice, chicken, and vegetables. Use {detail_lower} to plan the order, then name the first step, the reason it comes first, and the check you would make next.",
                f"Plan a simple dinner around {detail_lower}; choose the order, the heat, and the final check, then explain what you would do before serving.",
            ],
        }
        cat_templates = scenario_templates.get(scenario_name, [])
        if cat_templates:
            return random.choice(cat_templates)

    if _is_cooking_subject(spec):
        action, result = _cooking_practical_focus(concept, spec, retriever)
        concept_l = concept.lower()
        if "knife" in concept_l:
            templates = [
                f"Exercise: chop one onion into even slices, then say what changed when you kept the cuts steady and the pieces matched in size. Focus on grip, angle, and control.",
                f"Scenario: cut carrots into the same size pieces, then explain the first adjustment you made and why it improved control. Say whether the cuts felt safer, smoother, or more even.",
            ]
        elif "food safety" in concept_l:
            templates = [
                f"Scenario: you have raw chicken and salad ingredients. What is the first safe move, and how does that prevent contamination? Name the separation step and the storage step you would use next.",
                f"Exercise: choose the safest way to handle leftovers before serving. What do you do first, and what temperature check comes next? Explain how that keeps the food safe.",
            ]
        elif "ingredient science" in concept_l:
            templates = [
                f"Exercise: change only one thing, like heat or acid, then describe what happened to texture and flavor, and name the visible result. Keep the comparison to one variable only.",
                f"Scenario: you adjust one ingredient variable in a dish. What changes first, and how do you know the adjustment worked? Explain the before-and-after difference in plain language.",
            ]
        elif "flavor balance" in concept_l:
            templates = [
                f"Exercise: taste a dish and adjust only salt, acid, fat, or sweetness. What changes first, and what is the next taste check? Say which flavor you would test again afterward.",
                f"Scenario: your soup tastes flat. Which single flavor dial do you turn first, why that one, and what result are you looking for? Explain the effect on the final taste.",
            ]
        elif "kitchen workflow" in concept_l or "kitchen organization" in concept_l or "core kitchen flow" in concept_l:
            templates = [
                f"Scenario: your prep, cooking, and cleanup all overlap. What order do you choose, and what is the first thing you set up? Explain why that order keeps the station under control.",
                f"Exercise: plan the order for a simple dinner, then name the first station you set and why it comes first. Include the step that saves the most time.",
            ]
        else:
            templates = [
                f"Scenario: you are cooking dinner and the pan, board, and timer are all in use. Use {action}; then name the first move, the timing choice, and the check before you serve. Explain the effect on the dish.",
                f"Scenario: your sauce tastes flat. Use {action} and explain what changed in the flavor, then say what you would taste next. Keep the answer tied to one clear adjustment.",
                f"You have plain rice, chicken, and vegetables. Use {action} to make the meal balanced and explain the first thing you would do, plus the final check before serving. Say what result you are looking for.",
            ]
    else:
        if _is_history_subject(spec):
            templates = [
                f"Challenge: a player finds two conflicting accounts about {detail_lower}. Decide which account is stronger by naming the source type, placing it on the timeline, and explaining one consequence.",
                f"Scenario: a museum label about {concept} is too vague. Rewrite it using {detail_lower}, one date or period, and one cause-and-effect link so the visitor can see why it matters.",
                f"Quest: sort three clues about {concept}: a source, a date, and a consequence. Use {detail_lower} as the example, then explain which clue should come first and why.",
            ]
        else:
            templates = [
                f"What is one real-world example of {concept}, and why does it matter?",
                f"Use {detail} to solve a practical problem in one concrete case.",
                f"Describe one way {concept} changes the outcome of a real situation with a specific example.",
                f"Give a short explanation of {concept} using a concrete case like {detail}.",
            ]
    return random.choice(templates)


def generate_refusal_response(spec, boundary=None):
    subject = _subject_focus(spec)
    npc_name = spec["npc_name"]

    def _with_refusal_contract(text: str) -> str:
        lowered = text.lower()
        has_boundary = any(marker in lowered for marker in ["i can't", "i cannot", "i don't", "i do not", "outside"])
        has_redirect = "instead" in lowered or "i can help with" in lowered or "let's focus on" in lowered
        if not has_boundary:
            text = f"I can't help with that request. {text}"
            lowered = text.lower()
        if not has_redirect:
            text = f"{text} Instead, I can help with a concrete {subject} topic."
        return text

    if boundary:
        boundary_lower = boundary.lower()
        if _is_history_subject(spec):
            if "speculate" in boundary_lower or "speculation" in boundary_lower or "counterfactual" in boundary_lower:
                example = _example_topics(spec, limit=1)
                example = example[0] if example else "the fall of Rome"
                concrete = example.replace("What caused ", "").replace("?", "")
                templates = [
                    f"I can't treat counterfactuals as fact, so I would label that as speculation. Instead, we can stick to the real event and its sources, like {concrete}, then separate what happened from what people imagine might have happened.",
                    f"That is hypothetical, so I would mark it as speculation. Instead, I can help with the documented event, its chronology, and the evidence historians use to explain the actual outcome.",
                    f"I can't present an alternate outcome as fact. Instead, I can separate the speculation from what the sources actually show, then describe the documented cause and consequence.",
                ]
            elif "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
                templates = [
                    f"I can't help spread unsupported claims. Instead, I can help with verified chronology, sources, and evidence.",
                    f"I need to stay with evidence-based history. Let's focus on the documented version and the sources behind it.",
                    f"I can't endorse a conspiracy account without evidence. Instead, I can compare the claim with documented sources and scholarly consensus.",
                ]
            elif "unsupported certainty" in boundary_lower or "date range" in boundary_lower:
                templates = [
                    f"I can't give exact dates as if historians all agree, but I can share the commonly used range and why it is used.",
                    f"That question asks for more certainty than the evidence supports. Instead, I can give the standard range and the reason behind it.",
                ]
            elif "topic change" in boundary_lower or "different topic" in boundary_lower:
                templates = [
                    f"Absolutely — we can switch topics, and I can still help with a history topic like ancient civilizations, medieval history, or modern history.",
                    f"Yes, let's change direction. If you'd like, we can talk about the fall of Rome, the Middle Ages, or the printing press instead.",
                ]
            else:
                templates = [
                    f"That is outside my role as {npc_name}. Instead, I can help with chronology, sources, or evidence in {subject}.",
                    f"I can't help with that request. Instead, I can explain a documented {subject} topic about chronology or sources.",
                    f"I can't answer that directly. Let's focus on a real {subject} question about chronology, sources, or evidence.",
                    f"That sits outside what I cover. What I can do is help with a documented {subject} topic.",
                ]
            return _with_refusal_contract(random.choice(templates))
        if "speculate" in boundary_lower or "speculation" in boundary_lower or "counterfactual" in boundary_lower:
            example = _example_topics(spec, limit=1)
            example = example[0] if example else "the fall of Rome"
            concrete = example.replace("What caused ", "").replace("?", "")
            templates = [
                f"I can't treat counterfactuals as fact, so I would label them as speculation and stick to the real event, like {concrete}.",
                f"That is hypothetical, so I would mark it as speculation. A better {subject} question is how the real event unfolded, like {concrete}.",
            ]
        elif "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
            templates = [
                f"I can't help spread unsupported claims. Instead, I can help with verified {subject} information.",
                f"I need to stay with evidence-based {subject}. Let's focus on the documented version instead.",
            ]
        elif "aliens" in boundary_lower or "extraterrestrial" in boundary_lower:
            templates = [
                f"I can't confirm alien existence or appearance. Instead, I can explain how astronomers search for life using exoplanets and biosignatures.",
                f"I can't verify that claim. Let's focus on astronomy facts and current evidence.",
            ]
        elif "unsupported certainty" in boundary_lower or "date range" in boundary_lower:
            templates = [
                f"I can't give exact dates as if historians all agree, but I can share the commonly used range and why it is used.",
                f"That question asks for more certainty than the evidence supports. Instead, I can give the standard range and the reason behind it.",
            ]
        elif "medical" in boundary_lower or "dietary" in boundary_lower:
            if any(word in subject.lower() for word in ["cook", "culinary", "chef"]):
                templates = [
                    f"I can't make a diet plan or treat a medical condition. Instead, I can help with safe recipes and meal prep.",
                    f"I can't prescribe a diet, but I can walk you through a cooking technique or a simple balanced meal.",
                    f"I don't give medical or dietary advice. What I can do is share cooking techniques and balanced recipes.",
                    f"I don't handle treatment plans. Let's focus on safe cooking methods and flavor instead.",
                ]
            elif any(word in subject.lower() for word in ["fitness", "exercise"]):
                templates = [
                    f"I can't give personalized medical or dietary advice. Instead, I can help with safe training habits and recovery.",
                    f"That is outside my role as {npc_name}. I can explain form, consistency, and general fitness basics instead.",
                ]
            else:
                templates = [
                    f"I can't give personalized medical or dietary advice. Instead, I can help with general nutrition basics.",
                    f"That is outside my role as {npc_name}. I cannot prescribe diets, but I can cover safe meal-prep basics.",
                ]
        elif "unsafe" in boundary_lower or "food preparation" in boundary_lower:
            if _is_history_subject(spec):
                templates = [
                    f"I can't help with that safety question here. Instead, I can explain chronology, sources, or evidence in world history.",
                    f"That is outside my history role. I can help with a documented world history topic about chronology or sources.",
                    f"I can't answer that as a history guide. Instead, we can look at a source, a date range, or a turning point.",
                    f"That question is outside my scope. I can still help with evidence-based world history or source analysis.",
                ]
            elif any(word in subject.lower() for word in ["cook", "culinary", "chef"]):
                templates = [
                    f"I can't recommend unsafe preparation methods. Use a safer approach instead: keep food at safe temperatures, handle it cleanly, and cool leftovers promptly.",
                    f"That's unsafe and not safe to recommend. A safer option is to cook it properly, check the temperature, and store it right away.",
                    f"I don't recommend shortcuts that risk food safety. Cook it properly, cool leftovers promptly, and store them cold so the food stays safe and still tastes good.",
                    f"I don't handle methods that ignore safe cooking temperatures. I can help with a safer step instead, like cooling, reheating, or storage.",
                ]
            elif any(word in subject.lower() for word in ["fitness", "exercise"]):
                templates = [
                    f"I can't recommend unsafe preparation methods. Instead, I can help with a safer training or recovery alternative.",
                    f"Safety comes first, so I wouldn't endorse that approach. Let's focus on a lower-risk fitness alternative.",
                ]
            else:
                templates = [
                    f"I can't recommend unsafe preparation methods. Instead, I can help with a safer way to get a similar result.",
                    f"Safety comes first, so I wouldn't endorse that approach. Let's focus on a lower-risk alternative.",
                ]
        else:
            if any(word in subject.lower() for word in ["cook", "culinary", "chef"]):
                templates = [
                    f"That is outside my role as {npc_name}. Instead, I can help with a safe recipe, a technique, or a safer cooking alternative with a clear next step.",
                    f"I can't help with that request. I can still answer a safe cooking question or walk through a safer version of the dish with specific steps.",
                    f"I can't answer that directly. Let's focus on cooking fundamentals, food safety, or a safe recipe step you can use right away.",
                    f"That sits outside what I cover. What I can do is help with a documented cooking topic or a safer, useful alternative.",
                ]
            else:
                templates = [
                    f"That is outside my role as {npc_name}. Instead, I can help with a documented {subject} topic.",
                    f"I can't help with that request. Instead, I can explain a documented {subject} topic about chronology or sources.",
                    f"I can't answer that directly. Let's focus on a real {subject} question about chronology, sources, or evidence.",
                    f"That sits outside what I cover. What I can do is help with a documented {subject} topic.",
                    f"I don't cover that topic. Let's talk about {subject} instead - what would you like to learn?",
                    f"I don't handle requests outside {subject}. I can help with evidence, sources, or a concrete example.",
                ]
        return _with_refusal_contract(random.choice(templates))

    if _is_cooking_subject(spec):
        templates = [
            f"That is outside my role as {npc_name}. Instead, I can help with a safe recipe, a technique, or a safer cooking alternative with a clear next step.",
            f"I can't help with that request. I can still answer a safe cooking question or walk through a safer version of the dish with specific steps.",
            f"I can't answer that directly. Let's focus on cooking fundamentals, food safety, or a safe recipe step you can use right away.",
            f"That sits outside what I cover. What I can do is help with a documented cooking topic or a safer, useful alternative.",
            f"I don't cover that topic. Let's talk about safe cooking fundamentals instead - what would you like to learn, a technique or a recipe step?",
            f"I don't handle requests outside cooking fundamentals. I can help with safe techniques, ingredients, or a safer concrete example you can use.",
        ]
    else:
        templates = [
            f"I am {npc_name}, and I specialize in {subject}. That question is outside my area of expertise.",
            f"I focus on {subject}, so I can't help with that request. Ask me about a verified fact or a safe alternative instead.",
            f"As {npc_name}, I am here to help you explore {subject}. I cannot assist with that, but I can answer in-scope questions.",
            f"That is not something I can help with. My role is to teach {subject}.",
            f"I don't cover that area. Let me help with {subject} instead - pick a topic you want to explore.",
            f"I don't handle that kind of request. Ask me about {subject} and I'll give you a clear, helpful answer.",
        ]
    return _with_refusal_contract(random.choice(templates))
