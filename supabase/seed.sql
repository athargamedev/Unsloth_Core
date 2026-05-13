-- ============================================================
-- Seed Data for NPC Dashboard
-- Insert sample NPC profiles and test results
-- ============================================================

-- NPC Profiles
INSERT INTO npc_profiles (npc_id, npc_name, display_name, description, is_active) VALUES
    ('chemistry_instructor', 'Chemistry Instructor', 'Dr. Marie Curie', 'Expert chemistry tutor specializing in organic chemistry and lab safety. Teaches high school and college-level chemistry with practical demonstrations.', TRUE),
    ('bible_instructor', 'Bible Instructor', 'Biblical Scholar', 'Knowledgeable Bible study guide covering Old and New Testament history, theology, and practical application.', TRUE),
    ('physics_tutor', 'Physics Tutor', 'Prof. Albert Einstein', 'Physics tutor specializing in classical mechanics, thermodynamics, and quantum physics fundamentals.', FALSE),
    ('history_guide', 'History Guide', 'Historian AI', 'World history expert covering ancient civilizations through modern era with contextual analysis.', TRUE)
ON CONFLICT (npc_id) DO NOTHING;

-- Test Results (for leaderboard)
INSERT INTO test_results (npc_id, test_name, test_type, prompt_text, response_text, expected_response, score, metrics) VALUES
    ('chemistry_instructor', 'baseline-eval', 'summary', 'What is the pH scale?', 'The pH scale measures acidity from 0-14...', 'The pH scale measures how acidic or basic a substance is...', 0.92, '{"accuracy": 0.92, "coherence": 0.88, "relevance": 0.95, "hallucination": 0.02, "total_samples": 50}'),
    ('chemistry_instructor', 'lora-v1-eval', 'summary', 'Balance this equation: H2 + O2 → H2O', '2H2 + O2 → 2H2O. This is a synthesis reaction...', '2H2 + O2 → 2H2O', 0.97, '{"accuracy": 0.97, "coherence": 0.94, "relevance": 0.98, "hallucination": 0.01, "total_samples": 50}'),
    ('bible_instructor', 'baseline-eval', 'summary', 'Explain the parable of the Good Samaritan', 'The Good Samaritan parable from Luke 10:25-37 teaches...', 'A story Jesus told to illustrate loving your neighbor...', 0.85, '{"accuracy": 0.85, "coherence": 0.82, "relevance": 0.90, "hallucination": 0.05, "total_samples": 40}'),
    ('bible_instructor', 'lora-v2-eval', 'summary', 'What is the significance of the Exodus?', 'The Exodus is the foundational story of Israel''s deliverance...', 'The Exodus describes Israel''s liberation from Egyptian slavery...', 0.94, '{"accuracy": 0.94, "coherence": 0.91, "relevance": 0.96, "hallucination": 0.03, "total_samples": 40}'),
    ('history_guide', 'baseline-eval', 'summary', 'What caused the fall of Rome?', 'The fall of the Western Roman Empire resulted from...', 'A combination of economic decline, military overspending...', 0.88, '{"accuracy": 0.88, "coherence": 0.86, "relevance": 0.92, "hallucination": 0.04, "total_samples": 35}'),
    ('chemistry_instructor', 'lora-v3-eval', 'summary', 'What is the ideal gas law?', 'PV = nRT, where P is pressure, V is volume...', 'PV = nRT, where P = pressure, V = volume, n = moles...', 0.99, '{"accuracy": 0.99, "coherence": 0.97, "relevance": 0.99, "hallucination": 0.0, "total_samples": 50}')
ON CONFLICT DO NOTHING;
